from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import BigInteger, Boolean, String, Text, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.config import Lab, LabGroup


class Role(Base):
    __tablename__ = "roles"

    role_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    role_name: Mapped[str] = mapped_column(String(50), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to users
    users: Mapped[List["User"]] = relationship("User", back_populates="role")

    def __repr__(self) -> str:
        return f"<Role(role_name={self.role_name!r})>"


class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    role_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("roles.role_id"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    staff_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, unique=True
    )
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
    lab_group_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("lab_groups.lab_group_id"), nullable=True
    )
    lab_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("labs.lab_id"), nullable=True
    )
    reset_tokens: Mapped[List["PasswordResetToken"]] = relationship(
        "PasswordResetToken", back_populates="user", cascade="all, delete-orphan"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    # Relationships
    role: Mapped["Role"] = relationship("Role", back_populates="users")
    lab_group: Mapped[Optional["LabGroup"]] = relationship("LabGroup")
    lab: Mapped[Optional["Lab"]] = relationship("Lab")

    def __repr__(self) -> str:
        return f"<User(email={self.email!r}, full_name={self.full_name!r})>"


class PasswordResetToken(Base):
    __tablename__ = "password_reset_tokens"

    token_id: Mapped[int] = mapped_column(
        BigInteger, primary_key=True, autoincrement=True
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.user_id", ondelete="CASCADE"), nullable=False
    )
    temp_password: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    used: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to user
    user: Mapped["User"] = relationship("User", back_populates="reset_tokens")

    def __repr__(self) -> str:
        return f"<PasswordResetToken(user_id={self.user_id!r}, expires_at={self.expires_at!r}, used={self.used!r})>"
