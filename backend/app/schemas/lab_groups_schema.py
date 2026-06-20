from pydantic import BaseModel
from typing import Optional

class LabGroupRead(BaseModel):
    lab_group_id: int
    wbs_code: str
    lab_group_name: str

    class Config:
        from_attributes = True  # Allows Pydantic to read nested SQLAlchemy models

class UserResponse(BaseModel):
    id: int
    full_name: str
    email: str
    role: str
    lab_group_id: Optional[int] = None
    # This must be present for FastAPI to emit the data
    lab_group: Optional[LabGroupRead] = None 

    class Config:
        from_attributes = True