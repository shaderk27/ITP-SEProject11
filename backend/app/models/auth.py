from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import BigInteger, String, Text, DateTime, ForeignKey, Boolean, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Relationship back to users
    users: Mapped[List["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role(role_name={self.role_name!r})>"


# class LabGroup(Base):
#     __tablename__ = "lab_groups"

#     lab_group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
#     lab_group_name: Mapped[str] = mapped_column(String(120), nullable=False)
#     wbs_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
#     description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
#     created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

#     # Relationship back to users
#     users: Mapped[List["User"]] = relationship("User", back_populates="lab_group")

#     def __repr__(self) -> str:
#         return f"<LabGroup(lab_group_name={self.lab_group_name!r}, wbs_code={self.wbs_code!r})>"
class LabGroup(Base):
    __tablename__ = "lab_groups"

    lab_group_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lab_group_name: Mapped[str] = mapped_column(String(120), nullable=False)
    wbs_code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # Using Optional[str] to match User file styles
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())  # Fixed type & added func

    # Relationship to link users back to their lab group settings
    users: Mapped[List["User"]] = relationship("User", back_populates="lab_group")  # Standardized capitalization to List

    def __repr__(self) -> str:
        return f"<LabGroup(lab_group_name={self.lab_group_name!r}, wbs_code={self.wbs_code!r})>"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    role_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("roles.role_id"), nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    staff_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False, 
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )
    lab_group_id: Mapped[Optional[int]] = mapped_column(BigInteger, ForeignKey("lab_groups.lab_group_id"), nullable=True)

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    lab_group: Mapped[Optional["LabGroup"]] = relationship("LabGroup", back_populates="users")
    def __repr__(self) -> str:
        return f"<User(email={self.email!r}, full_name={self.full_name!r})>"