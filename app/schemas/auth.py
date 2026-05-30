"""
app/schemas/auth.py — Auth request and response schemas
=========================================================
Owner: B5 (SC-015)

Pydantic schemas define the shape of data coming INTO and going OUT
of the API. They are completely separate from SQLAlchemy models.

WHY SEPARATE FROM MODELS?
  SQLAlchemy models contain every field — hashed_password, is_active,
  internal flags. We never expose all of these to the client.
  Schemas are the deliberately limited API surface.
  This separation makes accidental data leakage structurally impossible.
  hashed_password cannot appear in a response — it is not in the schema.

REQUEST SCHEMAS — data coming IN:
  RegisterRequest → POST /auth/register
  LoginRequest    → POST /auth/login

RESPONSE SCHEMAS — data going OUT:
  TokenResponse       → returned after register and login
  UserProfileResponse → returned by GET /users/me
"""

import re
from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field, field_validator


# ------------------------------------------------------------------ #
# Request schemas
# ------------------------------------------------------------------ #

class RegisterRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/register.

    Pydantic validates this automatically before the route handler runs.
    Invalid email or weak password → 422 response, route never executes.
    """

    email: EmailStr = Field(
        description="Valid email address. Stored lowercase internally.",
        examples=["user@example.com"],
    )
    password: str = Field(
        min_length=8,
        max_length=128,
        description=(
            "Password. Minimum 8 characters, maximum 128. "
            "Must contain at least one letter and one number."
        ),
        examples=["SecurePass123"],
    )

    @field_validator("password")
    @classmethod
    def password_strength(cls, v: str) -> str:
        """
        Enforce minimum password complexity beyond just length.

        Rules enforced here (length enforced by Field):
          - At least one letter (upper or lower)
          - At least one digit

        These rules run BEFORE any database operation.
        A user with a weak password is rejected immediately.
        """
        if not re.search(r"[A-Za-z]", v):
            raise ValueError("Password must contain at least one letter.")
        if not re.search(r"\d", v):
            raise ValueError("Password must contain at least one number.")
        return v

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
            }
        }
    }


class LoginRequest(BaseModel):
    """
    Request body for POST /api/v1/auth/login.

    No password strength validation here — login checks whatever
    the user typed against the stored hash. Strength was validated
    at registration.
    """

    email: EmailStr = Field(
        description="Registered email address.",
        examples=["user@example.com"],
    )
    password: str = Field(
        description="Account password.",
        examples=["SecurePass123"],
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "email": "user@example.com",
                "password": "SecurePass123",
            }
        }
    }


# ------------------------------------------------------------------ #
# Response schemas
# ------------------------------------------------------------------ #

class TokenResponse(BaseModel):
    """
    Returned after successful registration or login.

    Client stores both tokens:
      access_token  → include in Authorization header on every API call
      refresh_token → store securely, use only to get a new access token

    token_type is always "bearer" — this is the OAuth2 standard.
    """

    access_token: str = Field(
        description="Short-lived JWT access token. Expires in 15 minutes.",
    )
    refresh_token: str = Field(
        description="Long-lived JWT refresh token. Expires in 7 days.",
    )
    token_type: str = Field(
        default="bearer",
        description="Token type. Always 'bearer'.",
    )

    model_config = {
        "json_schema_extra": {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
            }
        }
    }


class UserProfileResponse(BaseModel):
    """
    Returned by GET /api/v1/users/me.

    Deliberately limited — only fields safe to expose to the client.
    NOT included: hashed_password, is_active, updated_at.

    from_attributes=True — Pydantic reads fields directly from
    a SQLAlchemy ORM object. Without this, the response builder fails.

    sobriety_start_date is Optional[str] not Optional[date] because
    JSON serialisation of Python date objects is simpler as a string.
    """

    id: UUID = Field(description="User's unique identifier.")
    email: str = Field(description="User's email address.")
    framework_orientation: str = Field(
        description="Recovery framework orientation.",
    )
    sobriety_start_date: Optional[str] = Field(
        default=None,
        description="Sobriety start date in YYYY-MM-DD format. Null if not set.",
    )
    created_at: datetime = Field(description="Account creation timestamp.")

    model_config = {
        "from_attributes": True,
        "json_schema_extra": {
            "example": {
                "id": "123e4567-e89b-12d3-a456-426614174000",
                "email": "user@example.com",
                "framework_orientation": "aa",
                "sobriety_start_date": "2025-01-01",
                "created_at": "2025-01-15T08:30:00Z",
            }
        },
    }