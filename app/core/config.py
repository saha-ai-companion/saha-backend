"""
SC-001 — Config system
======================
Centralised configuration using Pydantic BaseSettings.

All environment variables are declared here with types and defaults.
Nothing is ever hardcoded. Secrets come from OS environment or a .env
file (local dev only — never commit .env to git).

Usage anywhere in the app:
    from app.core.config import settings
    print(settings.app_name)
"""

from enum import Enum
from functools import lru_cache
from typing import Optional

from pydantic import AnyHttpUrl, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(str, Enum):
    """Deployment environments. Controls logging format, debug mode, etc."""
    DEV = "dev"
    STAGING = "staging"
    PROD = "prod"


class Settings(BaseSettings):
    """
    All application configuration in one place.

    Pydantic automatically reads values from environment variables.
    Variable names are case-insensitive — APP_NAME and app_name both work.

    For local development, create a .env file in the project root.
    For EC2 / production, set environment variables directly (see infra/env-setup.md).
    Never commit .env to git — it is already in .gitignore.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        # extra fields in .env are ignored, not errors
        extra="ignore",
    )

    # ------------------------------------------------------------------ #
    # Application identity
    # ------------------------------------------------------------------ #
    app_name: str = Field(default="Saha Sobriety Companion", description="Human-readable app name")
    app_version: str = Field(default="0.1.0", description="Semantic version string")
    environment: Environment = Field(default=Environment.DEV, description="Deployment environment")

    # ------------------------------------------------------------------ #
    # API settings
    # ------------------------------------------------------------------ #
    api_v1_prefix: str = Field(default="/api/v1", description="URL prefix for all v1 routes")

    # ------------------------------------------------------------------ #
    # Security — JWT
    # ------------------------------------------------------------------ #
    jwt_secret_key: str = Field(
        ...,  # Required — no default. App will not start without this.
        description="Secret key for signing JWTs. Min 32 chars. Generate with: openssl rand -hex 32",
    )
    jwt_algorithm: str = Field(default="HS256", description="JWT signing algorithm")
    access_token_expire_minutes: int = Field(default=15, description="Access token lifetime in minutes")
    refresh_token_expire_days: int = Field(default=7, description="Refresh token lifetime in days")

    # ------------------------------------------------------------------ #
    # Database
    # ------------------------------------------------------------------ #
    database_url: str = Field(
        ...,  # Required — no default.
        description=(
            "PostgreSQL async connection string. "
            "Format: postgresql+asyncpg://user:password@host:port/dbname"
        ),
    )

    # ------------------------------------------------------------------ #
    # AI / LLM
    # ------------------------------------------------------------------ #
    anthropic_api_key: Optional[str] = Field(
        default=None,
        description="Anthropic API key for Claude. Required when AI features are active.",
    )
    openai_api_key: Optional[str] = Field(
        default=None,
        description="OpenAI API key. Optional — provider chosen in AI module.",
    )
    llm_provider: str = Field(
        default="anthropic",
        description="Active LLM provider: 'anthropic' or 'openai'",
    )
    llm_model: str = Field(
        default="claude-sonnet-4-20250514",
        description="Model identifier for the active provider",
    )
    llm_max_tokens: int = Field(
        default=512,
        description="Maximum tokens in companion response. Keep low — companion is concise by design.",
    )
    conversation_window_size: int = Field(
        default=20,
        description="Number of past turns injected into every prompt (prototype memory strategy)",
    )

    # ------------------------------------------------------------------ #
    # CORS — allowed origins for the React Native frontend
    # ------------------------------------------------------------------ #
    allowed_origins: list[AnyHttpUrl] = Field(
        default=[],
        description="List of allowed CORS origins. Add Expo dev server URL locally.",
    )

    # ------------------------------------------------------------------ #
    # Logging
    # ------------------------------------------------------------------ #
    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG, INFO, WARNING, ERROR, CRITICAL",
    )

    # ------------------------------------------------------------------ #
    # Feature flags — disable features during early prototype phase
    # ------------------------------------------------------------------ #
    ai_enabled: bool = Field(
        default=False,
        description="Enable Claude API calls. Set False until SC-028 is complete.",
    )
    memory_enabled: bool = Field(
        default=False,
        description="Enable memory injection into prompts. Set False until SC-029 is complete.",
    )

    # ------------------------------------------------------------------ #
    # Validators
    # ------------------------------------------------------------------ #
    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        valid = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if v.upper() not in valid:
            raise ValueError(f"log_level must be one of {valid}")
        return v.upper()

    @field_validator("jwt_secret_key")
    @classmethod
    def validate_jwt_secret(cls, v: str) -> str:
        if len(v) < 32:
            raise ValueError("jwt_secret_key must be at least 32 characters. Generate with: openssl rand -hex 32")
        return v

    # ------------------------------------------------------------------ #
    # Convenience properties
    # ------------------------------------------------------------------ #
    @property
    def is_dev(self) -> bool:
        return self.environment == Environment.DEV

    @property
    def is_prod(self) -> bool:
        return self.environment == Environment.PROD


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Return the cached Settings singleton.

    lru_cache ensures .env is read exactly once per process.
    Use this function as a FastAPI dependency:

        from fastapi import Depends
        from app.core.config import get_settings, Settings

        @router.get("/something")
        def my_route(settings: Settings = Depends(get_settings)):
            ...

    Or import the module-level singleton for non-route code:

        from app.core.config import settings
        print(settings.app_name)
    """
    return Settings()


# Module-level singleton — convenience import for non-DI usage
settings: Settings = get_settings()
