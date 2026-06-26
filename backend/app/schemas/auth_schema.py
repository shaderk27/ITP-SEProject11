from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ==========================================
# REQUEST SCHEMAS
# ==========================================


class LoginRequest(BaseModel):
    """Validates the incoming login credentials."""

    email: EmailStr = Field(
        ..., description="The user's registered institutional email address"
    )
    password: str = Field(..., min_length=1, description="Plaintext password")

    # In Pydantic v2, 'Config' becomes 'model_config'
    model_config = {
        "json_schema_extra": {
            "example": {"email": "admin@test.local", "password": "your_secure_password"}
        }
    }


# ==========================================
# RESPONSE SCHEMAS (Sanitized User Objects)
# ==========================================


class UserBaseResponse(BaseModel):
    """Base fields shared across user profile payload responses."""

    id: int = Field(..., serialization_alias="id")
    full_name: str
    email: EmailStr
    role: Optional[str] = Field(
        None, description="Assigned role name (e.g., admin, teamlead, labic)"
    )


class LoginResponse(BaseModel):
    """Structure returned upon successful authentication alongside the set cookie."""

    message: str = "Successfully logged in"
    user: UserBaseResponse


class CurrentUserResponse(UserBaseResponse):
    """Detailed response structure returned by the /me endpoint."""

    staff_id: Optional[str] = Field(
        None, description="Unique institutional employee identifier"
    )
    lab_group_id: Optional[int] = Field(
        None, description="Associated primary lab group cluster identifier, if scoped"
    )

    class Config:
        # Allows Pydantic to read data seamlessly if you pass a raw SQLAlchemy model instance
        from_attributes = True


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    role_id: int
    staff_id: Optional[str] = None
    lab_group_id: Optional[int] = None
    lab_id: Optional[int] = None


class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None
    current_password: Optional[str] = None
    new_password: Optional[str] = Field(None, min_length=8, description="Must be at least 8 characters")
class ForgotPasswordSchema(BaseModel):
    email: str
class LabICOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    lab_id: Optional[int]
class AssignLabSchema(BaseModel):
    lab_id: int
class AssignLabGroupSchema(BaseModel):
    lab_group_id: int
    class Config:
        from_attributes = True