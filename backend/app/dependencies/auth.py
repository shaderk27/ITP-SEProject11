"""
Authentication dependency for FastAPI endpoints.

Today: header-based identity (X-User-Email) for dev/demo.
After W7-02: swap the body of get_current_user() to decode a real token.
Every endpoint that uses `Depends(get_current_user)` keeps working unchanged.
"""

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.auth import User


def get_current_user(
    x_user_email: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the current request's caller into a User row.

    Strict mode:
      - 401 if no X-User-Email header sent (no identity claim).
      - 404 if header is sent but doesn't match any seeded user.

    When real auth ships:
      - Replace the header read with token decode / session lookup.
      - Return the same User type.
      - All endpoints using Depends(get_current_user) keep working.
    """
    if not x_user_email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-User-Email header. Log in first.",
        )

    user = db.query(User).filter(User.email == x_user_email).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"User '{x_user_email}' not found. "
                "Did you log in with a seeded email? See backend/seeds/dev_seed.sql."
            ),
        )
    return user
