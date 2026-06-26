"""
Authentication dependency for FastAPI endpoints.

Primary path: reads the JWT `access_token` cookie that Tim's auth flow
(W7-02) sets on login. Decodes the JWT with the shared SECRET_KEY,
looks up the user by `sub` (user_id) claim, and returns the User row.

Transition fallback: while frontend services still send `X-User-Email`,
fall back to header-based lookup so the UI keeps working between
Chunks 1A and 2A. Fallback removed in Chunk 3A.
"""
from typing import Optional

import jwt
from fastapi import Cookie, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.auth import User
from app.services.auth_service import ALGORITHM, COOKIE_NAME, SECRET_KEY


def get_current_user(
    access_token: Optional[str] = Cookie(default=None, alias=COOKIE_NAME),
    x_user_email: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    """
    Resolve the current request's caller into a User row.

    Priority:
      1. `access_token` JWT cookie (Tim's real auth — primary).
      2. `X-User-Email` header (legacy shim — kept for the W9-02 transition,
         removed in Chunk 3A once all frontend services use credentials cookies).

    Raises:
      - 401 if no valid identity (no cookie, no header, or token invalid/expired).
      - 404 if the resolved identity does not match any DB user.
    """
    if access_token:
        try:
            payload = jwt.decode(access_token, SECRET_KEY, algorithms=[ALGORITHM])
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired. Please log in again.",
            )
        except jwt.InvalidTokenError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid session token.",
            )

        user_id_str = payload.get("sub")
        if not user_id_str:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed session token.",
            )

        try:
            user_id = int(user_id_str)
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Malformed session token.",
            )

        user = db.query(User).filter(User.user_id == user_id).first()
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists.",
            )
        return user

    # Legacy header fallback — only used until Chunk 2A lands.
    if x_user_email:
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

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated. Log in first.",
    )
