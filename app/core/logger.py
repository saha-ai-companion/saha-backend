"""
SC-004 — Structured logger
==========================
Structured JSON logging for production; human-readable output for dev.

Why structured logging?
    When this backend runs on EC2, logs go to CloudWatch. Structured JSON
    logs are queryable — you can filter by user_id, request_id, level, etc.
    Plain text logs are not. For a clinical product under HIPAA, this is
    not optional — audit trails must be searchable.

Usage anywhere in the app:
    from app.core.logger import get_logger

    log = get_logger(__name__)
    log.info("user_registered", user_id=str(user.id), email_domain="gmail.com")
    log.error("db_connection_failed", error=str(e))

IMPORTANT — never log PHI:
    Do NOT log: full email addresses, conversation content, user 'why',
    trigger mappings, or any health-related user data.
    DO log: user_id (UUID), request_id, endpoint, status_code, duration_ms.
"""

import logging
import sys

import structlog
from structlog.types import EventDict, WrappedLogger

from app.core.config import settings


def _drop_color_message_key(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """
    Uvicorn adds a 'color_message' key with ANSI escape codes.
    Remove it so it does not pollute JSON logs.
    """
    event_dict.pop("color_message", None)
    return event_dict


def _add_app_info(
    logger: WrappedLogger, method_name: str, event_dict: EventDict
) -> EventDict:
    """Stamp every log line with app name and version for CloudWatch filtering."""
    event_dict["app"] = settings.app_name
    event_dict["version"] = settings.app_version
    event_dict["env"] = settings.environment.value
    return event_dict


def setup_logging() -> None:
    """
    Configure structlog and Python's standard logging.

    Call this once at application startup in main.py.
    All subsequent calls to get_logger() inherit this configuration.

    Dev mode  → pretty coloured output, human readable, timestamped
    Prod mode → JSON output, one line per event, machine parseable
    """
    log_level = getattr(logging, settings.log_level)

    # Shared processors that run on every log event regardless of mode
    shared_processors: list = [
        structlog.contextvars.merge_contextvars,       # injects request_id from context
        structlog.stdlib.add_log_level,                 # adds "level": "info"
        structlog.stdlib.add_logger_name,               # adds "logger": "app.api.v1.health"
        structlog.processors.TimeStamper(fmt="iso"),    # ISO-8601 timestamp
        _drop_color_message_key,
        _add_app_info,
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,           # formats exceptions inline
    ]

    if settings.is_dev:
        # Pretty output for local development
        renderer = structlog.dev.ConsoleRenderer(colors=True)
    else:
        # JSON for production — one line per event, CloudWatch friendly
        renderer = structlog.processors.JSONRenderer()

    structlog.configure(
        processors=shared_processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    # Also configure Python's standard logging so third-party libraries
    # (SQLAlchemy, uvicorn, httpx) route through structlog
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=log_level,
    )
    for name in logging.root.manager.loggerDict:
        logging.getLogger(name).handlers = []
        logging.getLogger(name).propagate = True


def get_logger(name: str) -> structlog.BoundLogger:
    """
    Return a named structlog logger.

    Args:
        name: Module name. Always pass __name__:
              log = get_logger(__name__)

    Returns:
        A structlog BoundLogger with all processors configured.
    """
    return structlog.get_logger(name)


# ------------------------------------------------------------------ #
# Request ID middleware support
# ------------------------------------------------------------------ #
# Request ID is bound to structlog's context vars at the start of
# each request in main.py middleware. Every log line in that request
# automatically includes the request_id without passing it explicitly.

def bind_request_id(request_id: str) -> None:
    """Bind request_id into the current async context."""
    structlog.contextvars.bind_contextvars(request_id=request_id)


def clear_request_context() -> None:
    """Clear context vars at the end of each request."""
    structlog.contextvars.clear_contextvars()
