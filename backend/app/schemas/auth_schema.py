from typing import Optional
from pydantic import BaseModel, EmailStr, Field


# ==========================================
# REQUEST SCHEMAS
# ==========================================

class LoginRequest(BaseModel):
    """Validates the incoming login credentials."""
    email: EmailStr = Field(..., description="The user's registered institutional email address")
    password: str = Field(..., min_length=1, description="Plaintext password")

    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@test.local",
                "password": "your_secure_password"
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
    role: Optional[str] = Field(None, description="Assigned role name (e.g., admin, teamlead, labic)")


class LoginResponse(BaseModel):
    """Structure returned upon successful authentication alongside the set cookie."""
    message: str = "Successfully logged in"
    user: UserBaseResponse


class CurrentUserResponse(UserBaseResponse):
    """Detailed response structure returned by the /me endpoint."""
    staff_id: Optional[str] = Field(None, description="Unique institutional employee identifier")
    lab_group_id: Optional[int] = Field(None, description="Associated primary lab group cluster identifier, if scoped")

    class Config:
        # Allows Pydantic to read data seamlessly if you pass a raw SQLAlchemy model instance 
        from_attributes = True