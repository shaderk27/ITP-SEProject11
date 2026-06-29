"""
SQLAlchemy models for the `users` and `roles` tables.

These tables already exist in the DB (created by the initial schema).
This file just exposes them to the Python side so endpoints can query them.
"""

from sqlalchemy import BigInteger, Column, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class Role(Base):
    __tablename__ = "roles"

    role_id = Column(BigInteger, primary_key=True)
    role_name = Column(String(50), nullable=False, unique=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class User(Base):
    __tablename__ = "users"

    user_id = Column(BigInteger, primary_key=True)
    role_id = Column(BigInteger, ForeignKey("roles.role_id"), nullable=False)
    full_name = Column(String(150), nullable=False)
    email = Column(String(255), nullable=False, unique=True)
    staff_id = Column(String(50), unique=True)
    password_hash = Column(Text, nullable=False)
    # Team Leads are scoped to one lab group; Admin/Lab IC leave this NULL.
    lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())

    role = relationship("Role")
    lab_group = relationship("LabGroup")
