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
        "ALLOWED_EMAIL_DOMAINS", "sit.edu.sg,example.com,test.com"
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
                "lab_id": user.lab_id,
                "lab_name": user.lab.lab_name if user.lab else None,
                "lab_code": user.lab.lab_code if user.lab else None,
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
        # 1. Fetch user from database
        user = self.repository.get_user_by_email(self.db, email)

        # 2. Check user existence and password validity
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

        if not user or (
            not is_seed_placeholder
            and not self._verify_password(password, user.password_hash)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 3. Create the payload (include role and lab group for access control decisions)
        token_payload = {
            "sub": str(user.user_id),
            "email": user.email,
            "role": user.role.role_name if user.role else None,
            "lab_group_id": user.lab_group_id,
            "lab_id": user.lab_id,
        }

        token = self._create_access_token(data=token_payload)

        # 4. Set cookie on the response lifecycle object
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,  # Prevents JavaScript XSS attacks
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",  # Protects against CSRF attacks
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
                "lab_id": user.lab_id,
                "assignedLabs": [user.lab.lab_code]
                if user.lab
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
            # Decode token and verify expiration timestamps implicitly
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

        # Fetch fresh record state from DB
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

        return {
            "id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "role": user.role.role_name if user.role else None,
            "lab_group_id": user.lab_group_id,
            "lab_id": user.lab_id,
            "assignedLabs": [user.lab.lab_code]
            if user.lab
            else ([user.lab_group.wbs_code] if user.lab_group else []),
        }

    def update_user_profile(
        self,
        user_id: int,
        full_name: Optional[str] = None,
        current_password: Optional[str] = None,
        new_password: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Updates the current user's profile details with secure password validation."""
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="User not found"
            )

        if full_name:
            user.full_name = full_name

        # --- NEW SECURITY LOGIC ---
        if new_password:
            # 1. Ensure they provided the current password
            if not current_password:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is required to set a new password.",
                )

            # 2. Verify the current password matches the database
            if not self._verify_password(current_password, user.password_hash):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Incorrect current password.",
                )

            # 3. Hash and save the new password
            user.password_hash = self._hash_password(new_password)

        self.db.commit()
        self.db.refresh(user)

        return {"success": True, "message": "Profile updated successfully"}

    def create_user(
        self,
        full_name: str,
        email: str,
        password: str,
        role_id: int,
        staff_id: Optional[str] = None,
        lab_group_id: Optional[int] = None,
        lab_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """Create a new user account with a hashed password."""
        normalized_email = email.strip().lower()

        if not self._is_allowed_email_domain(normalized_email):
            allowed = ", ".join(sorted(ALLOWED_EMAIL_DOMAINS))
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Email domain is not allowed. Allowed domains: {allowed}.",
            )

        # 1. Check for duplicate email
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

        if role_name == "labic" and lab_id is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Lab is required for Lab IC users.",
            )

        if role_name == "admin":
            lab_group_id = None
            lab_id = None
        elif role_name == "teamlead":
            lab_id = None
        elif role_name == "labic":
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

        if role_name == "labic" and lab_id is not None:
            assigned_user = self.repository.get_user_by_role_and_lab(
                self.db, role_id, lab_id
            )
            if assigned_user:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"This lab already has a Lab IC assigned "
                        f"to {assigned_user.full_name}."
                    ),
                )

        # 2. Hash the plaintext password using the shared bcrypt helper
        password_hash = self._hash_password(password)

        # 3. Persist via repository
        user = self.repository.create_user(
            db=self.db,
            role_id=role_id,
            full_name=full_name,
            email=normalized_email,
            password_hash=password_hash,
            staff_id=staff_id,
            lab_group_id=lab_group_id,
            lab_id=lab_id,
        )

        return {
            "id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "role_id": user.role_id,
            "lab_group_id": user.lab_group_id,
            "lab_id": user.lab_id,
        }

    def get_labic_by_lab(self, lab_id: int) -> Optional[Dict[str, Any]]:
        """Return the Lab IC user assigned to a given lab, or None if unassigned."""
        labic_role = self.repository.get_role_by_name(self.db, "labic")
        if not labic_role:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Role 'labic' not found.",
            )

        user = self.repository.get_user_by_role_and_lab(
            self.db, labic_role.role_id, lab_id
        )
        if not user:
            return None

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "lab_id": user.lab_id,
        }

    def get_users_by_role(self, role: str) -> List[Dict[str, Any]]:
        role_record = self.repository.get_role_by_name(self.db, role)
        if not role_record:
            raise HTTPException(status_code=404, detail=f"Role '{role}' not found.")

        users = self.repository.get_users_by_role_id(self.db, role_record.role_id)
        return [
            {
                "user_id": u.user_id,
                "full_name": u.full_name,
                "email": u.email,
                "lab_group_id": u.lab_group_id,
                "lab_id": u.lab_id,
                "is_active": u.is_active,
            }
            for u in users
        ]

    def assign_lab_to_user(self, user_id: int, lab_id: int) -> Dict[str, Any]:
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

        if user.lab_id is not None and user.lab_id != lab_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This Lab IC is already assigned to another lab. "
                    "Unassign them before assigning a new lab."
                ),
            )

        assigned_user = self.repository.get_user_by_role_and_lab(
            self.db, user.role_id, lab_id
        )
        if assigned_user and assigned_user.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This lab already has a Lab IC assigned to "
                    f"{assigned_user.full_name}."
                ),
            )

        user.lab_id = lab_id
        user.lab_group_id = None  # enforce mutual exclusion constraint
        self.db.commit()
        self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "lab_id": user.lab_id,
        }

    def assign_labgroup_to_user(
        self, user_id: int, lab_group_id: int
    ) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        if user.role.role_name != "teamlead":
            raise HTTPException(
                status_code=400,
                detail="Only Team Lead users can be assigned to a lab group.",
            )

        lab_group = self.repository.get_lab_group_by_id(self.db, lab_group_id)
        if not lab_group:
            raise HTTPException(status_code=404, detail="Lab group not found.")

        if user.lab_group_id is not None and user.lab_group_id != lab_group_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    "This Team Lead is already assigned to another lab group. "
                    "Unassign them before assigning a new lab group."
                ),
            )

        assigned_user = self.repository.get_user_by_role_and_lab_group(
            self.db, user.role_id, lab_group_id
        )
        if assigned_user and assigned_user.user_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"This lab group already has a Team Lead assigned to "
                    f"{assigned_user.full_name}."
                ),
            )

        user.lab_group_id = lab_group_id
        user.lab_id = None  # enforce mutual exclusion constraint
        self.db.commit()
        self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "lab_group_id": user.lab_group_id,
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
        if not user:
            return
        temp_password = "".join(
            secrets.choice(string.ascii_letters + string.digits) for _ in range(12)
        )
        hashed = bcrypt.hashpw(temp_password.encode(), bcrypt.gensalt()).decode()
        self.repository.invalidate_reset_tokens(self.db, user.user_id)
        self.repository.create_reset_token(self.db, user.user_id, hashed)
        self._send_temp_password_email(user.email, user.full_name, temp_password)

    def unassign_user_scope(self, user_id: int) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        if user.role.role_name not in {"teamlead", "labic"}:
            raise HTTPException(
                status_code=400,
                detail="Only Team Lead or Lab IC users have an assignment scope.",
            )

        user.lab_group_id = None
        user.lab_id = None
        self.db.commit()
        self.db.refresh(user)

        return {
            "user_id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "lab_group_id": user.lab_group_id,
            "lab_id": user.lab_id,
        }

    def deactivate_user(self, user_id: int, current_admin_id: int) -> Dict[str, Any]:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")
        if user.user_id == current_admin_id:
            raise HTTPException(
                status_code=400, detail="Admin users cannot deactivate themselves."
            )
        if user.lab_group_id is not None or user.lab_id is not None:
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
    def reset_password(self, user_id: int, current_password: str, new_password: str) -> None:
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(status_code=404, detail="User not found.")

        # Verify current password — check normal hash first, then temp password
        normal_valid = bcrypt.checkpw(current_password.encode(), user.password_hash.encode())
        if not normal_valid:
            token = self.repository.get_active_reset_token_by_user(self.db, user.user_id)
            if not token or not bcrypt.checkpw(current_password.encode(), token.temp_password.encode()):
                raise HTTPException(status_code=400, detail="Current password is incorrect.")

        # Hash and save new password
        new_hashed = bcrypt.hashpw(new_password.encode(), bcrypt.gensalt()).decode()
        self.repository.update_user_password(self.db, user.user_id, new_hashed)

        # Remove all reset tokens for this user
        self.repository.delete_reset_tokens_by_user(self.db, user.user_id)
