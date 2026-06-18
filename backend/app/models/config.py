from sqlalchemy import Column, BigInteger, String, Text, Boolean, Numeric, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from pydantic import BaseModel

class LabGroup(Base):
    __tablename__ = "lab_groups"
    
    lab_group_id = Column(BigInteger, primary_key=True)
    lab_group_name = Column(String(120), nullable=False)
    wbs_code = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    labs = relationship("Lab", back_populates="group")

class Lab(Base):
    __tablename__ = "labs"
    
    lab_id = Column(BigInteger, primary_key=True)
    lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    lab_code = Column(String(50))
    lab_name = Column(String(150), nullable=False)
    venue = Column(Text)
    is_general = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    group = relationship("LabGroup", back_populates="labs")
    aliases = relationship("LabAlias", back_populates="lab")

class LabAlias(Base):
    __tablename__ = "lab_aliases"
    
    lab_alias_id = Column(BigInteger, primary_key=True)
    lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    alias_text = Column(String(200), nullable=False)
    alias_type = Column(String(50))
    
    lab = relationship("Lab", back_populates="aliases")

class RequesterLabMapping(Base):
    __tablename__ = "requester_lab_mappings"
    
    requester_mapping_id = Column(BigInteger, primary_key=True)
    requester_name = Column(String(150), nullable=False)
    requester_email = Column(String(255))
    default_lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    confidence_note = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class SpendingCategory(Base):
    __tablename__ = "spending_categories"
    
    category_id = Column(BigInteger, primary_key=True)
    category_name = Column(String(100), nullable=False)
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Budget(Base):
    __tablename__ = "budgets"
    
    budget_id = Column(BigInteger, primary_key=True)
    period_id = Column(BigInteger)
    lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    category_id = Column(BigInteger, ForeignKey("spending_categories.category_id"))
    budget_amount = Column(Numeric(14, 2))
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

# --- PYDANTIC SCHEMAS FOR API RESPONSES ---
 
class LabGroupOut(BaseModel):
    id: int
    name: str
    budget: int
    threshold: int

class LabOut(BaseModel):
    id: int
    code: str
    name: str
    group: str
    budget: int
    ic: str

# --- NEW: PYDANTIC SCHEMAS FOR CREATING/EDITING ---
class LabGroupCreate(BaseModel):
    name: str
    wbs_code: str
    description: str | None = None