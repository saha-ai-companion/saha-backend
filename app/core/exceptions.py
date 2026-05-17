"""
SC-005 — Exception handling
============================
Two things live here:
  1. Custom exception classes for domain-specific errors
  2. Global exception handlers registered on the FastAPI app

Why this matters for a clinical product:
    Raw stack traces must NEVER reach the client. They leak implementation
    details, can expose PHI field names, and look unprofessional. Every
    error the client receives is a controlled JSON response.

    Stack traces ARE logged server-side (structlog) so engineers can debug.
    The log includes the request_id, which correlates to the client's error
    response for support purposes.

Error response shape (consistent across all endpoints):
    {
        "error": "auth_error",
        "message": "Invalid credentials.",
        "request_id": "a3f9c2d1-...",
        "status_code": 401
    }
"""

import uuid
from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logger import get_logger

log = get_logger(__name__)


# ------------------------------------------------------------------ #
# Domain exception classes
# Each maps to a specific HTTP status and error code.
# Raise these from service/repository layers — never raise HTTPException
# directly from business logic.
# ------------------------------------------------------------------ #

class AppException(Exception):
    """Base class for all application exceptions."""
    status_code: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "internal_error"
    message: str = "An unexpected error occurred."

    def __init__(self, message: str | None = None, **context: Any):
        self.message = message or self.__class__.message
        self.context = context  # Extra data for logging — never sent to client
        super().__init__(self.message)


class AuthError(AppException):
    """Authentication or authorisation failure."""
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "auth_error"
    message = "Authentication required."


class ForbiddenError(AppException):
    """User authenticated but not allowed to access this resource."""
    status_code = status.HTTP_403_FORBIDDEN
    error_code = "forbidden"
    message = "You do not have permission to access this resource."


class NotFoundError(AppException):
    """Requested resource does not exist."""
    status_code = status.HTTP_404_NOT_FOUND
    error_code = "not_found"
    message = "The requested resource was not found."


class ConflictError(AppException):
    """Resource already exists or state conflict."""
    status_code = status.HTTP_409_CONFLICT
    error_code = "conflict"
    message = "A conflict occurred with the current state of the resource."


class ValidationError(AppException):
    """Business rule validation failure (distinct from Pydantic schema validation)."""
    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "validation_error"
    message = "The request could not be processed due to a validation error."


class MemoryError(AppException):
    """Failure in the companion memory layer."""
    status_code = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "memory_error"
    message = "A memory system error occurred."


class AIProviderError(AppException):
    """LLM API call failure."""
    status_code = status.HTTP_502_BAD_GATEWAY
    error_code = "ai_provider_error"
    message = "The AI provider is currently unavailable. Please try again shortly."


class CrisisDetectedError(AppException):
    """
    Crisis signal detected in companion conversation.
    Triggers escalation protocol — not a standard error flow.
    """
    status_code = status.HTTP_200_OK  # 200 — crisis response IS a valid response
    error_code = "crisis_detected"
    message = "Crisis protocol activated."


# ------------------------------------------------------------------ #
# Error response builder
# ------------------------------------------------------------------ #

def _error_response(
    status_code: int,
    error_code: str,
    message: str,
    request_id: str,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": error_code,
            "message": message,
            "request_id": request_id,
            "status_code": status_code,
        },
    )


def _get_request_id(request: Request) -> str:
    """Extract request_id from state (set by middleware in main.py)."""
    return getattr(request.state, "request_id", str(uuid.uuid4()))


# ------------------------------------------------------------------ #
# Exception handlers — registered on the FastAPI app in main.py
# ------------------------------------------------------------------ #

async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    """Handle all custom AppException subclasses."""
    request_id = _get_request_id(request)
    log.warning(
        "app_exception",
        error_code=exc.error_code,
        status_code=exc.status_code,
        message=exc.message,
        request_id=request_id,
        path=request.url.path,
        **exc.context,
    )
    return _error_response(exc.status_code, exc.error_code, exc.message, request_id)


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    """Handle FastAPI/Starlette HTTP exceptions (raised by fastapi directly)."""
    request_id = _get_request_id(request)
    log.warning(
        "http_exception",
        status_code=exc.status_code,
        detail=str(exc.detail),
        request_id=request_id,
        path=request.url.path,
    )
    return _error_response(exc.status_code, "http_error", str(exc.detail), request_id)


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """
    Handle Pydantic request schema validation errors.

    Formats the validation errors into a readable message.
    Raw Pydantic error output is not returned to the client.
    """
    request_id = _get_request_id(request)
    errors = exc.errors()
    # Build a human-readable summary without exposing internal field paths
    messages = []
    for err in errors:
        loc = " → ".join(str(l) for l in err["loc"] if l != "body")
        messages.append(f"{loc}: {err['msg']}" if loc else err["msg"])
    message = "; ".join(messages) if messages else "Invalid request data."

    log.warning(
        "request_validation_error",
        error_count=len(errors),
        request_id=request_id,
        path=request.url.path,
    )
    return _error_response(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "validation_error",
        message,
        request_id,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Catch-all for any exception not handled above.

    Logs the full traceback server-side.
    Returns a generic 500 — no stack trace to client, ever.
    """
    request_id = _get_request_id(request)
    log.error(
        "unhandled_exception",
        exc_info=exc,
        request_id=request_id,
        path=request.url.path,
    )
    return _error_response(
        status.HTTP_500_INTERNAL_SERVER_ERROR,
        "internal_error",
        "An unexpected error occurred. Please try again.",
        request_id,
    )


# ------------------------------------------------------------------ #
# Registration helper — called in main.py
# ------------------------------------------------------------------ #

def register_exception_handlers(app: FastAPI) -> None:
    """
    Register all exception handlers on the FastAPI app.

    Call this in main.py after creating the app instance.
    Order matters — more specific handlers must be registered first.
    """
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
