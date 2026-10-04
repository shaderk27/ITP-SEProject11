from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

# ==========================================
# REQUEST SCHEMAS
# ==========================================


class LoginRequest(BaseModel):
    """Validates incoming login credentials."""

    email: EmailStr = Field(
        ..., description="The user's registered institutional email address"
    )
    password: str = Field(..., min_length=1, description="Plaintext password")

    model_config = {
        "json_schema_extra": {
            "example": {"email": "admin@test.local", "password": "your_secure_password"}
        }
    }


# ==========================================
# RESPONSE SCHEMAS
# ==========================================


class UserLabAssignmentResponse(BaseModel):
    lab_id: int
    is_primary: bool

    model_config = ConfigDict(from_attributes=True)


class UserBaseResponse(BaseModel):
    """Base fields shared across user profile payload responses."""

    id: int = Field(..., serialization_alias="id")
    full_name: str
    email: EmailStr
    role: Optional[str] = Field(
        None, description="Assigned role name (e.g., admin, teamlead, labic)"
    )
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


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
    lab_ids: List[int] = Field(
        default_factory=list, description="IDs of labs where user is assigned as IC"
    )

    model_config = ConfigDict(from_attributes=True)


class CreateUserRequest(BaseModel):
    full_name: str
    email: EmailStr
    password: str = Field(..., min_length=8)
    role_id: int
    staff_id: Optional[str] = None
    lab_group_id: Optional[int] = None
    lab_ids: Optional[List[int]] = Field(
        default=None, description="List of lab IDs to assign this user to"
    )
    primary_lab_id: Optional[int] = Field(
        default=None, description="Lab ID to mark as primary for this user"
    )


class RoleResponse(BaseModel):
    role_id: int
    role_name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UpdateProfileRequest(BaseModel):
    full_name: Optional[str] = None


class ForgotPasswordSchema(BaseModel):
    email: str
    new_password: Optional[str] = Field(
        None, min_length=8, description="Must be at least 8 characters"
    )


class LabICOut(BaseModel):
    user_id: int
    full_name: str
    email: str
    lab_ids: List[int] = []
    is_primary: bool = False

    model_config = ConfigDict(from_attributes=True)


class AssignLabSchema(BaseModel):
    lab_id: int
    is_primary: Optional[bool] = None


class AssignLabGroupSchema(BaseModel):
    lab_group_id: int


class ResetPasswordSchema(BaseModel):
    current_password: Optional[str] = None
    new_password: str

    @field_validator("new_password")
    @classmethod
    def validate_new_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters.")
        return v