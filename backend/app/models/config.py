from sqlalchemy import (
    Column,
    BigInteger,
    Integer,
    String,
    Text,
    Boolean,
    Numeric,
    DateTime,
    ForeignKey,
    Date,
    UniqueConstraint,
    Index,
    text,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.database import Base
from pydantic import BaseModel

# --- SQLALCHEMY DATABASE MODELS ---


class LabGroup(Base):
    __tablename__ = "lab_groups"

    lab_group_id = Column(BigInteger, primary_key=True)
    lab_group_name = Column(String(120), nullable=False)
    wbs_code = Column(String(100))
    description = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # --- LAB GROUP ENVELOPE THRESHOLDS ---
    notified_50 = Column(Boolean, default=False)
    notified_80 = Column(Boolean, default=False)
    notified_95 = Column(Boolean, default=False)
    notified_100 = Column(Boolean, default=False)
    alert_period_id = Column(
        BigInteger, ForeignKey("budget_periods.period_id"), nullable=True
    )

    labs = relationship("Lab", back_populates="group")


class Lab(Base):
    __tablename__ = "labs"

    lab_id = Column(BigInteger, primary_key=True)
    lab_group_id = Column(
        BigInteger,
        ForeignKey("lab_groups.lab_group_id", ondelete="SET NULL"),
        nullable=True,
    )
    lab_code = Column(String(50))
    lab_name = Column(String(150), nullable=False)
    venue = Column(Text)
    is_general = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    group = relationship("LabGroup", back_populates="labs")
    aliases = relationship("LabAlias", back_populates="lab")
    # Lab ICs (many-to-many via lab_ic_assignments): any number per lab, at most one primary.
    ic_assignments = relationship(
        "LabIcAssignment",
        back_populates="lab",
        cascade="all, delete-orphan",
        order_by="LabIcAssignment.assignment_id",
    )

    # --- INDIVIDUAL LAB THRESHOLDS ---
    notified_50 = Column(Boolean, default=False)
    notified_80 = Column(Boolean, default=False)
    notified_95 = Column(Boolean, default=False)
    notified_100 = Column(Boolean, default=False)
    alert_period_id = Column(
        BigInteger, ForeignKey("budget_periods.period_id"), nullable=True
    )

    @property
    def primary_ic(self):
        """The primary Lab IC (User) or None."""
        for a in self.ic_assignments:
            if a.is_primary:
                return a.user
        return None

    @property
    def ic_users(self):
        """All Lab ICs (Users), primary first."""
        ordered = sorted(
            self.ic_assignments, key=lambda a: (not a.is_primary, a.assignment_id or 0)
        )
        return [a.user for a in ordered]

    @property
    def ic_user(self):
        """Back-compat for code written against the 1-1 model: the primary IC, else the
        first assigned IC, else None. Read-only. New code should use primary_ic / ic_users."""
        return self.primary_ic or (self.ic_users[0] if self.ic_assignments else None)


class LabIcAssignment(Base):
    """A user acting as Lab IC for a lab. Many-to-many; at most one primary per lab."""

    __tablename__ = "lab_ic_assignments"
    __table_args__ = (
        UniqueConstraint("lab_id", "user_id", name="uq_lab_ic_lab_user"),
        Index(
            "uq_lab_ic_one_primary",
            "lab_id",
            unique=True,
            postgresql_where=text("is_primary"),
        ),
    )

    assignment_id = Column(BigInteger, primary_key=True)
    lab_id = Column(
        BigInteger, ForeignKey("labs.lab_id", ondelete="CASCADE"), nullable=False
    )
    user_id = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    is_primary = Column(Boolean, nullable=False, default=False)
    assigned_at = Column(DateTime(timezone=True), server_default=func.now())
    assigned_by = Column(
        BigInteger, ForeignKey("users.user_id", ondelete="SET NULL"), nullable=True
    )

    lab = relationship("Lab", back_populates="ic_assignments")
    user = relationship(
        "User", back_populates="lab_assignments", foreign_keys=[user_id]
    )
    assigned_by_user = relationship("User", foreign_keys=[assigned_by])


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


class BudgetPeriod(Base):
    __tablename__ = "budget_periods"

    period_id = Column(BigInteger, primary_key=True)
    period_name = Column(String(50), nullable=False, unique=True)
    year_no = Column(Integer, nullable=False)
    start_date = Column(Date)
    end_date = Column(Date)
    is_closed = Column(Boolean, nullable=False, default=False)


class Budget(Base):
    __tablename__ = "budgets"

    budget_id = Column(BigInteger, primary_key=True)
    period_id = Column(BigInteger)
    lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    lab_id = Column(
        BigInteger, ForeignKey("labs.lab_id"), nullable=True
    )  # Explicitly nullable for envelopes
    category_id = Column(
        BigInteger, ForeignKey("spending_categories.category_id"), nullable=True
    )  # Explicitly nullable for envelopes
    budget_amount = Column(Numeric(14, 2))
    created_by = Column(BigInteger)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


# --- PYDANTIC API SCHEMAS ---


class LabGroupOut(BaseModel):
    id: int
    name: str
    wbs_code: str | None = None
    description: str | None = None
    budget: float  # The Total Envelope
    allocated_to_labs: float  # How much is given to labs
    unallocated: float  # Remaining available
    spent: float = 0.0
    threshold: int


class LabIcOut(BaseModel):
    user_id: int
    name: str
    email: str
    is_primary: bool


class LabOut(BaseModel):
    id: int
    code: str
    name: str
    group: str
    group_id: int
    venue: str | None = None
    budget: float
    spent: float = 0.0
    ic_name: str | None = None
    ic_email: str | None = None  # primary IC (kept for existing clients)
    ics: list[LabIcOut] = []  # all Lab ICs, primary first
    budgets: dict[str, float] = {}
    spent_by_category: dict[str, float] = {}


class CategoryOut(BaseModel):
    id: int
    name: str
    description: str | None = None


class LabGroupCreate(BaseModel):
    name: str
    wbs_code: str
    description: str | None = None
    budget: float = 0.0  # Support adding the envelope budget on creation
    assigned_lab_ids: list[int] | None = []


class CategoryCreate(BaseModel):
    name: str
    description: str | None = None


class LabCreate(BaseModel):
    lab_code: str
    lab_name: str
    lab_group_id: int
    venue: str | None = None
    ic_name: str | None = None
    ic_email: str | None = None
    budgets: dict[str, float] = {}
