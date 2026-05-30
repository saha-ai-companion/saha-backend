"""
app/repositories/user_repository.py — User data access layer
==============================================================
Owner: B1

Repository pattern — all database queries for the User model live here.

WHO CALLS THIS:
  Services call repository functions.
  Repository functions talk to the database.
  Routes never write SQL directly.
  Services never write SQL directly.

WHY THIS PATTERN:
  - Routes and services stay clean — no SQL anywhere except here
  - Database change? Only repositories change.
  - Easy to mock in unit tests

ALL FUNCTIONS ARE ASYNC.
  Every SQLAlchemy call uses await.
  Never use synchronous SQLAlchemy in this codebase.

PHI REMINDER:
  Never log email addresses — PII.
  Never log sobriety_start_date — PHI.
  Log user_id (UUID) only.
"""

from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logger import get_logger
from app.models.user import User

log = get_logger(__name__)


async def get_user_by_id(
    db: AsyncSession,
    user_id: UUID,
) -> Optional[User]:
    """
    Fetch a User by UUID primary key.

    Returns None if no user exists with that ID.
    Used by the protected route dependency to load the current user.

    Args:
        db: Async database session from get_db() dependency.
        user_id: The user's UUID.

    Returns:
        User ORM object if found, None otherwise.
    """
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    return result.scalar_one_or_none()


async def get_user_by_email(
    db: AsyncSession,
    email: str,
) -> Optional[User]:
    """
    Fetch a User by email address.

    Always normalises email to lowercase before querying.
    Returns None if no user exists with that email.

    Used by login to find the user before password verification.

    Args:
        db: Async database session.
        email: Email to look up. Will be lowercased and stripped.

    Returns:
        User ORM object if found, None otherwise.
    """
    result = await db.execute(
        select(User).where(
            User.email == email.lower().strip()
        )
    )
    return result.scalar_one_or_none()


async def create_user(
    db: AsyncSession,
    email: str,
    hashed_password: str,
) -> User:
    """
    Create a new User record.

    Does NOT commit — get_db() handles commit after route returns.
    db.flush() sends the INSERT to get the generated UUID without
    committing the transaction. If anything fails later in the
    same request, the rollback removes this record as if it never existed.

    Args:
        db: Async database session.
        email: User's email. Stored lowercase.
        hashed_password: bcrypt hash from security.hash_password().
                         NEVER pass plain password here.

    Returns:
        The newly created User ORM object with id populated.
    """
    user = User(
        email=email.lower().strip(),
        hashed_password=hashed_password,
    )
    db.add(user)
    await db.flush()

    log.info("user_created", user_id=str(user.id))
    return user


async def email_exists(
    db: AsyncSession,
    email: str,
) -> bool:
    """
    Check if an email address is already registered.

    Checks BEFORE attempting INSERT — gives a clean 409 ConflictError
    rather than a raw database unique constraint violation error.

    Selects only User.id not the full User object — faster because
    less data is transferred from PostgreSQL.

    Args:
        db: Async database session.
        email: Email to check. Will be lowercased.

    Returns:
        True if already registered, False if available.
    """
    result = await db.execute(
        select(User.id).where(
            User.email == email.lower().strip()
        )
    )
    return result.scalar_one_or_none() is not None