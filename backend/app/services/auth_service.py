from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
import smtplib
from typing import List, Optional, Dict, Any
import os

from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session
import jwt
import bcrypt
import secrets
import string

from app.config import load_environment
from app.repositories.auth_repository import AuthRepository

load_environment()

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-only-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
COOKIE_NAME = "access_token"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
ALLOW_PLACEHOLDER_PASSWORDS = (
    os.getenv("ALLOW_PLACEHOLDER_PASSWORDS", "true").lower() == "true"
)
ALLOWED_EMAIL_DOMAINS = {
    domain.strip().lower()
    for domain in os.getenv(
        "ALLOWED_EMAIL_DOMAINS", "sit.edu.sg,example.com,test.com,singaporetech.edu.sg"
    ).split(",")
    if domain.strip()
}
SMTP_HOST = os.getenv("SMTP_HOST", "SMTP_HOST is not set in environment")
SMTP_USER = os.getenv("SMTP_USER", "SMTP_USER is not set in environment")
SMTP_PASS = os.getenv("SMTP_PASS", "SMTP_PASS is not set in environment")


class AuthService:
    def __init__(self, repository: AuthRepository, db: Session):
        self.repository = repository
        self.db = db

    def _hash_password(self, password: str) -> str:
        """Hash a plaintext password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def _verify_password(self, plaintext_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against its stored bcrypt hash."""
        try:
            return bcrypt.checkpw(
                plaintext_password.encode("utf-8"), hashed_password.encode("utf-8")
            )
        except Exception:
            return False

    def _is_allowed_email_domain(self, email: str) -> bool:
        domain = email.rsplit("@", 1)[-1].lower()
        return domain in ALLOWED_EMAIL_DOMAINS

    def get_all_roles(self) -> List[Dict[str, Any]]:
        """Retrieve all roles available in the system."""
        roles = self.repository.get_all_roles(self.db)
        return [
            {"role_id": role.role_id, "role_name": role.role_name} for role in roles
        ]

    def _format_user_assignments(self, user) -> List[Dict[str, Any]]:
        """Helper to safely format lab assignments array."""
        if not hasattr(user, "lab_assignments") or not user.lab_assignments:
            return []
        return [
            {
                "lab_id": a.lab_id,
                "is_primary": a.is_primary,
                "assigned_at": a.assigned_at.isoformat() if a.assigned_at else None,
            }
            for a in user.lab_assignments
        ]

    def get_all_users(self) -> List[Dict[str, Any]]:
        users = self.repository.get_all_users(self.db)
        return [
            {
                "id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.role_name if user.role else None,
                "role_id": user.role_id,
                "lab_group_id": user.lab_group_id,
                "lab_group_name": user.lab_group.lab_group_name
                if user.lab_group
                else None,
                "lab_group_code": user.lab_group.wbs_code if user.lab_group else None,
                "lab_assignments": self._format_user_assignments(user),
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
            for user in users
        ]

    def get_assignments(self) -> list[dict]:
        return self.repository.get_assignments(self.db)

    def _create_access_token(
        self, data: dict, expires_delta: Optional[timedelta] = None
    ) -> str:
        """Generate a signed JWT token containing user metadata."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(
                minutes=ACCESS_TOKEN_EXPIRE_MINUTES
            )

        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def login(self, email: str, password: str, response: Response) -> Dict[str, Any]:
        """Authenticate a user, generate a JWT, and attach it as an HTTP-only cookie."""
        user = self.repository.get_user_by_email(self.db, email)
        if user and not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive.",
            )
        is_seed_placeholder = (
            ALLOW_PLACEHOLDER_PASSWORDS
            and user
            and user.password_hash == "placeholder_no_auth_yet"
        )
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        normal_valid = is_seed_placeholder or self._verify_password(
            password, user.password_hash
        )
        used_temp_password = False
        if not normal_valid:
            reset_token = self.repository.get_active_reset_token_by_user(
                self.db, user.user_id
            )
            if not reset_token or not self._verify_password(
                password, reset_token.temp_password
            ):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect email or password",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            self.repository.mark_token_used(self.db, reset_token)
            used_temp_password = True

        assigned_lab_ids = [a.lab_id for a in getattr(user, "lab_assignments", [])]
        assigned_lab_codes = [
            a.lab.lab_code
            for a in getattr(user, "lab_assignments", [])
            if hasattr(a, "lab") and a.lab
        ]

        token_payload = {
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role.role_name if user.role else None,
            "lab_group_id": user.lab_group_id,
            "lab_ids": assigned_lab_ids,
            "must_reset_password": used_temp_password,
        }
        token = self._create_access_token(data=token_payload)
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",
            secure=COOKIE_SECURE,
            path="/",
        )
        return {
            "message": "Successfully logged in",
            "user": {
                "id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "staff_id": user.staff_id,
                "role": user.role.role_name if user.role else None,
                "lab_group_id": user.lab_group_id,
                "lab_ids": assigned_lab_ids,
                "must_reset_password": used_temp_password,
                "assignedLabs": assigned_lab_codes
                if assigned_lab_codes
                else ([user.lab_group.wbs_code] if user.lab_group else []),
            },
        }

    def get_current_user(self, token: Optional[str]) -> Dict[str, Any]:
        """Validate an active JWT cookie token and return sanitized session user data."""
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

        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists.",
            )
        if not user.is_active:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive.",
            )

        assigned_lab_ids = [a.lab_id for a in getattr(user, "lab_assignments", [])]
        assigned_lab_codes = [
            a.lab.lab_code
            for a in getattr(user, "lab_assignments", [])
            if hasattr(a, "lab") and a.lab
        ]

        return {
            "id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "role": user.role.role_name if user.role else None,
            "lab_group_id": user.lab_group_id,
            "lab_ids": assigned_lab_ids,
            "must_reset_password": bool(payload.get("must_reset_password", False)),
            "assignedLabs": assigned_lab_codes
            if assigned_lab_codes
            else ([user.lab_group.wbs_code] if user.lab_group else []),
        }

    def _send_temp_password_email(
        self, email: str, name: str, temp_password: str
    ) -> None:
        msg = MIMEText(
            f"Hi {name},\n\n"
            f"Your temporary password is: {temp_password}\n\n"
            f"It expires in 1 hour. Please log in and change your password immediately.\n\n"
            f"If you did not request this, please contact your administrator."
        )
        msg["Subject"] = "Your Temporary Password"
        msg["From"] = SMTP_USER
        msg["To"] = email

        with smtplib.SMTP(SMTP_HOST, 587) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)

    def forgot_password(self, email: str) -> None:
        user = self.repository.get_user_by_email(self.db, email)
        if not user or not user.is_active:
            return
        temp_password = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(12)
        )
        hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
        self.repository.invalidate_reset_tokens(self.db, user.user_id)
        self.repository.create_reset_token(self.db, user.user_id, hashed)
        self._send_temp_password_email(user.email, user.full_name, temp_password)

    def update_user_profile(
        self,
        user_id: int,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found."
            )
        if full_name:
            user.full_name = full_name
        self.db.commit()
        self.db.refresh(user)
        return {"success": True, "message": "Profile updated successfully."}

    def create_user(
        self,
        full_name: str,
        email: str,
        password: str,
        role_id: int,
        staff_id: Optional[str] = None,
        lab_group_id: Optional[int] = None,
        lab_id: Optional[int] = None,
        lab_ids: Optional[List[int]] = None,
        primary_lab_id: Optional[int] = None,
        creator_admin_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new user account and process lab assignments."""
        normalized_email = email.strip().lower()

        if not self._is_allowed_email_domain(normalized_email):
            allowed = ", ".join(sorted(ALLOWED_EMAIL_DOMAINS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email domain is not allowed. Allowed domains: {allowed}.",
            )

        existing = self.repository.get_user_by_email(self.db, normalized_email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists.",
            )

        role = self.repository.get_role_by_id(self.db, role_id)
        if not role:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Selected role does not exist.",
            )

        role_name = role.role_name.lower()
        if role_name == "teamlead" and lab_group_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lab group is required for Team Lead users.",
            )

        if role_name in ["admin", "labic"]:
            lab_group_id = None

        if role_name == "teamlead" and lab_group_id is not None:
            assigned_user = self.repository.get_user_by_role_and_lab_group(
                self.db, role_id, lab_group_id
            )
            if assigned_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"This lab group already has a {role.role_name} assigned "
                        f"to {assigned_user.full_name}."
                    ),
                )

        password_hash = self._hash_password(password)

        user = self.repository.create_user(
            db=self.db,
            role_id=role_id,
            full_name=full_name,
            email=normalized_email,
            password_hash=password_hash,
            staff_id=staff_id,
            lab_group_id=lab_group_id,
        )

        # Process multiple or single lab assignments for Lab IC users
        if role_name == "labic":
            # Collect lab IDs to assign (supporting both list and single lab_id)
            target_lab_ids = set(lab_ids or [])
            if lab_id is not None:
                target_lab_ids.add(lab_id)

            # Determine primary lab (fallback to first lab if not explicitly provided)
            effective_primary_id = primary_lab_id or (
                next(iter(target_lab_ids)) if target_lab_ids else None
            )

            for target_lab_id in target_lab_ids:
                is_primary = target_lab_id == effective_primary_id
                self.repository.assign_lab_to_user(
                    db=self.db,
                    user_id=user.user_id,
                    lab_id=target_lab_id,
                    is_primary=is_primary,
                    assigned_by=creator_admin_id,
                )

        # Refresh user instance to ensure relationships (like lab_assignments) are loaded
        self.db.refresh(user)
        refreshed_user = self.repository.get_user_by_id(self.db, user.user_id) or user

        return {
            "id": refreshed_user.user_id,
            "full_name": refreshed_user.full_name,
            "email": refreshed_user.email,
            "staff_id": refreshed_user.staff_id,
            "role_id": refreshed_user.role_id,
            "lab_group_id": refreshed_user.lab_group_id,
            "lab_assignments": self._format_user_assignments(refreshed_user),
        }

    def assign_lab_to_user(
        self,
        user_id: int,
        lab_id: int,
        is_primary: Optional[bool] = None,
        assigned_by: Optional[int] = None,
    ) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        if user.role.role_name != "labic":
            raise HTTPException(
                status_code=400, detail="Only Lab IC users can be assigned to a lab."
            )

        lab = self.repository.get_lab_by_id(self.db, lab_id)
        if not lab:
            raise HTTPException(status_code=404, detail="Lab not found.")

        user.lab_group_id = None
        self.repository.assign_lab_to_user(
            self.db,
            user.user_id,
            lab_id,
            is_primary=is_primary,
            assigned_by=assigned_by,
        )
        self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "lab_assignments": self._format_user_assignments(user),
        }

    def assign_labgroup_to_user(
        self, user_id: int, lab_group_id: int
    ) -> Dict[str, Any]:
        """Assign a user (e.g., Team Lead / Team IC) to a specific lab group."""
        # 1. Check if user exists
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        # 2. (Optional) Verify lab group exists if repository method available
        if hasattr(self.repository, "get_lab_group_by_id"):
            lab_group = self.repository.get_lab_group_by_id(self.db, lab_group_id)
            if not lab_group:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Lab group not found",
                )

        # 3. Update lab group assignment in repository
        updated = self.repository.assign_labgroup_to_user(
            self.db, user_id=user_id, lab_group_id=lab_group_id
        )
        # Fallback to initial user object if the repo method returns None or void
        updated_user = (
            updated or self.repository.get_user_by_id(self.db, user_id) or user
        )
        return {
            "message": "User assigned to lab group successfully",
            "user_id": updated_user.user_id,
            "lab_group_id": updated_user.lab_group_id,
        }

    # def unassign_user_scope(self, user_id: int) -> Dict[str, Any]:
    #     user = self.repository.get_user_by_id(self.db, user_id)
    #     if not user:
    #         raise HTTPException(status_code=404, detail="User not found.")

    #     if user.role.role_name not in {"teamlead", "labic"}:
    #         raise HTTPException(
    #             status_code=400,
    #             detail="Only Team Lead or Lab IC users have an assignment scope.",
    #         )

    #     user.lab_group_id = None
    #     self.repository.unassign_all_labs_from_user(self.db, user.user_id, commit=False)
    #     self.db.commit()
    #     self.db.refresh(user)

    #     return {
    #         "user_id": user.user_id,
    #         "full_name": user.full_name,
    #         "email": user.email,
    #         "lab_group_id": user.lab_group_id,
    #         "lab_assignments": self._format_user_assignments(user),
    #     }

    def deactivate_user(self, user_id: int, current_admin_id: int) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        if user.user_id == current_admin_id:
            raise HTTPException(
                status_code=400, detail="Admin users cannot deactivate themselves."
            )

        has_assignments = bool(getattr(user, "lab_assignments", []))
        if user.lab_group_id is not None or has_assignments:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Unassign the user before deactivating the account.",
            )
        if not user.is_active:
            return {
                "user_id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "is_active": user.is_active,
            }

        user.is_active = False
        self.db.commit()
        self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "is_active": user.is_active,
        }

    def activate_user(
        self, user_id: int, current_admin_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Activate a user account with optional admin audit tracking."""
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found.",
            )

        if not user.is_active:
            user.is_active = True
            # Store admin audit reference if your model supports updated_by/activated_by
            if hasattr(user, "updated_by") and current_admin_id is not None:
                setattr(user, "updated_by", current_admin_id)

            self.db.commit()
            self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "is_active": user.is_active,
        }

    def reset_password(
        self, user_id: int, current_password: Optional[str], new_password: str
    ) -> None:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        is_placeholder = (
            ALLOW_PLACEHOLDER_PASSWORDS
            and user.password_hash == "placeholder_no_auth_yet"
        )

        if is_placeholder:
            pass
        elif current_password:
            normal_valid = bcrypt.checkpw(
                current_password.encode(), user.password_hash.encode()
            )
            if not normal_valid:
                token = self.repository.get_last_reset_token_by_user(
                    self.db, user.user_id
                )
                if not token or not bcrypt.checkpw(
                    current_password.encode(), token.temp_password.encode()
                ):
                    raise HTTPException(
                        status_code=400, detail="Current password is incorrect."
                    )
        else:
            token = self.repository.get_last_reset_token_by_user(self.db, user.user_id)
            if not token:
                raise HTTPException(
                    status_code=400, detail="Current password is required."
                )

        new_hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.repository.update_user_password(self.db, user.user_id, new_hashed)
        self.repository.delete_reset_tokens_by_user(self.db, user.user_id)

    def get_current_user_allow_reset(self, token: Optional[str]) -> Dict[str, Any]:
        """Like get_current_user but allows JWTs flagged with must_reset_password."""
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

        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User account no longer exists.",
            )

        return {
            "id": user.user_id,
            "must_reset_password": bool(payload.get("must_reset_password", False)),
        }

    def get_users_by_role(self, role: Optional[str] = None) -> List[Dict[str, Any]]:
        """Retrieve users, optionally filtered by role name."""
        if role:
            users = self.repository.get_users_by_role(self.db, role)
        else:
            users = self.repository.get_all_users(self.db)

        return [
            {
                "id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.role_name if user.role else None,
                "role_id": user.role_id,
                "lab_group_id": user.lab_group_id,
                "lab_group_name": user.lab_group.lab_group_name
                if user.lab_group
                else None,
                "lab_group_code": user.lab_group.wbs_code if user.lab_group else None,
                "lab_assignments": self._format_user_assignments(user),
                "is_active": user.is_active,
                "created_at": user.created_at.isoformat() if user.created_at else None,
            }
            for user in users
        ]

    def unassign_user_scope(self, user_id: int) -> Dict[str, str]:
        """Clear all lab assignments or group scope assignments for a given user."""
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        # Unassign lab assignments
        self.repository.unassign_all_labs_from_user(self.db, user_id, commit=False)

        # Clear lab_group_id assignment on user record if relevant
        if hasattr(user, "lab_group_id"):
            user.lab_group_id = None

        self.db.commit()
        return {"message": f"Scope and lab assignments cleared for user ID {user_id}"}

    def unassign_lab_from_user(self, user_id: int, lab_id: int) -> Dict[str, str]:
        """Remove a single lab IC assignment for a given user."""
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")

        self.repository.unassign_lab_from_user(self.db, user_id, lab_id)
        return {"message": f"Lab {lab_id} unassigned from user ID {user_id}"}
