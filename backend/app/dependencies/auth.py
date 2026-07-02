"""
Authentication dependency for FastAPI endpoints.

Reads the `access_token` JWT cookie set by /api/auth/login (Tim's W7-02
auth flow), decodes it with the shared SECRET_KEY/HS256 config, and
looks up the user by the `sub` (user_id) claim.

Returns the User model so endpoints can keep using
`current_user.role.role_name`, `current_user.lab_group_id`, etc.
"""

from typing import Any, Dict, Optional

import jwt
from fastapi import Cookie, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.auth import User
from app.services.auth_service import ALGORITHM, COOKIE_NAME, SECRET_KEY


def get_current_user(self, token: Optional[str]) -> Dict[str, Any]:
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Missing session token.",
        )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id_str: Optional[str] = payload.get("sub")
        if user_id_str is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token session metrics.",
            )
        user_id = int(user_id_str)
    except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session expired or signature invalid.",
        )

    must_reset_password = bool(payload.get("must_reset_password", False))

    user = self.repository.get_user_by_id(self.db, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer exists.",
        )

    # Block access to normal endpoints if password reset is required
    if must_reset_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password reset required before accessing this resource.",
        )

    return {
        "id": user.user_id,
        "full_name": user.full_name,
        "email": user.email,
        "staff_id": user.staff_id,
        "role": user.role.role_name if user.role else None,
        "lab_group_id": user.lab_group_id,
        "lab_id": user.lab_id,
        "must_reset_password": must_reset_password,
        "assignedLabs": [user.lab.lab_code]
        if user.lab
        else ([user.lab_group.wbs_code] if user.lab_group else []),
    }
