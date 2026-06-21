from datetime import datetime, timedelta, timezone
from typing import List, Optional, Dict, Any
from fastapi import HTTPException, Response, status
from sqlalchemy.orm import Session, joinedload
import jwt
import bcrypt

from app.models.auth import User  
from app.repositories.auth_repository import AuthRepository

# --- Configuration Constants ---
SECRET_KEY = "SUPER_SECRET_DEVELOPMENT_KEY_CHANGE_ME_IN_PRODUCTION"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
COOKIE_NAME = "access_token"


class AuthService:
    def __init__(self, repository: AuthRepository, db: Session):
        self.repository = repository
        self.db = db

    def _hash_password(self, password: str) -> str:
        """Hash a plaintext password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def _verify_password(self, plaintext_password: str, hashed_password: str) -> bool:
        """Verify a plaintext password against its stored bcrypt hash."""
        try:
            return bcrypt.checkpw(
                plaintext_password.encode('utf-8'), 
                hashed_password.encode('utf-8')
            )
        except Exception:
            return False
    def get_all_roles(self) -> List[Dict[str, Any]]:
        """Retrieve all roles available in the system."""
        roles = self.repository.get_all_roles(self.db)
        return [
            {
                "role_id": role.role_id,
                "role_name": role.role_name
            }
            for role in roles
        ]
    def _create_access_token(self, data: dict, expires_delta: Optional[timedelta] = None) -> str:
        """Generate a signed JWT token containing user metadata."""
        to_encode = data.copy()
        if expires_delta:
            expire = datetime.now(timezone.utc) + expires_delta
        else:
            expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        
        to_encode.update({"exp": expire})
        encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
        return encoded_jwt

    def login(self, email: str, password: str, response: Response) -> Dict[str, Any]:
        """Authenticate a user, generate a JWT, and attach it as an HTTP-only cookie."""
        # 1. Fetch user from database
        user = self.repository.get_user_by_email(self.db, email)
        
        # 2. Check user existence and password validity
        # If password hash is 'placeholder_no_auth_yet' (from dev_seed.sql), bypass check for easier initial testing
        is_seed_placeholder = user and user.password_hash == "placeholder_no_auth_yet"
        
        if not user or (not is_seed_placeholder and not self._verify_password(password, user.password_hash)):
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
            "lab_group_id": user.lab_group_id
        }
        
        token = self._create_access_token(data=token_payload)

        # 4. Set cookie on the response lifecycle object
        response.set_cookie(
            key=COOKIE_NAME,
            value=token,
            httponly=True,       # Prevents JavaScript XSS attacks
            max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            expires=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
            samesite="lax",      # Protects against CSRF attacks
            secure=False,        # Set to True in production over HTTPS
            path="/"
        )

        return {
            "message": "Successfully logged in",
            "user": {
                "id": user.user_id,
                "full_name": user.full_name,
                "email": user.email,
                "role": user.role.role_name if user.role else None
            }
        }

    def get_current_user(self, token: Optional[str]) -> Dict[str, Any]:
        """Validate an active JWT cookie token and return sanitized session user data."""
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Not authenticated. Missing session token."
            )

        try:
            # Decode token and verify expiration timestamps implicitly
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            user_id_str: Optional[str] = payload.get("sub")
            
            if user_id_str is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED, 
                    detail="Invalid token session metrics."
                )
                
            user_id = int(user_id_str)
            
        except (jwt.ExpiredSignatureError, jwt.InvalidTokenError, ValueError):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Session expired or signature invalid."
            )

        # Fetch fresh record state from DB
        user = self.repository.get_user_by_id(self.db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="User account no longer exists."
            )

        return {
            "id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "role": user.role.role_name if user.role else None,
            "lab_group_id": user.lab_group_id,
            "assignedLabs": [user.lab_group.wbs_code] if user.lab_group else []
        }
    def create_user(
        self,
        full_name: str,
        email: str,
        password: str,
        role_id: int,
        staff_id: Optional[str] = None,
        lab_group_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """Create a new user account with a hashed password."""

        # 1. Check for duplicate email
        existing = self.repository.get_user_by_email(self.db, email)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists."
            )

        # 2. Hash the plaintext password using the shared bcrypt helper
        password_hash = self._hash_password(password)

        # 3. Persist via repository
        user = self.repository.create_user(
            db=self.db,
            role_id=role_id,
            full_name=full_name,
            email=email,
            password_hash=password_hash,
            staff_id=staff_id,
            lab_group_id=lab_group_id
        )

        return {
            "id": user.user_id,
            "full_name": user.full_name,
            "email": user.email,
            "staff_id": user.staff_id,
            "role_id": user.role_id,
            "lab_group_id": user.lab_group_id
        }