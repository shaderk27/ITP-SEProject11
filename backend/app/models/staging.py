"""
SQLAlchemy models for the upload + staging + review-queue pipeline.

Mirrors the existing Postgres schema:
  upload_batches → staging_pr_headers → staging_pr_lines → review_queue_items
"""
from sqlalchemy import (
    BigInteger,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.database import Base


class UploadBatch(Base):
    __tablename__ = "upload_batches"

    batch_id = Column(BigInteger, primary_key=True)
    uploaded_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    filename = Column(String(255), nullable=False)
    file_type = Column(String(20), nullable=False)
    # Lifecycle: review_pending → ready_to_commit → committed (or failed).
    upload_status = Column(String(30), nullable=False)
    validation_message = Column(Text)
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    processed_at = Column(DateTime(timezone=True))

    uploader = relationship("User")
    headers = relationship("StagingPRHeader", back_populates="batch", cascade="all, delete-orphan")


class StagingPRHeader(Base):
    __tablename__ = "staging_pr_headers"

    staging_header_id = Column(BigInteger, primary_key=True)
    batch_id = Column(BigInteger, ForeignKey("upload_batches.batch_id"), nullable=False)
    source_pr_number = Column(String(50), nullable=False)
    req_type = Column(String(150))
    pr_sub_date = Column(Date)
    requestor_name = Column(String(150))
    purpose = Column(Text)
    grand_total_sgd = Column(Numeric(14, 2))
    wbs_code = Column(String(100))
    instruction_to_vendor = Column(Text)
    # Full original parsed header row, for forensics.
    raw_header_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    batch = relationship("UploadBatch", back_populates="headers")
    lines = relationship("StagingPRLine", back_populates="header", cascade="all, delete-orphan")


class StagingPRLine(Base):
    __tablename__ = "staging_pr_lines"

    staging_line_id = Column(BigInteger, primary_key=True)
    staging_header_id = Column(BigInteger, ForeignKey("staging_pr_headers.staging_header_id"), nullable=False)
    source_line_no = Column(Integer)
    item_details = Column(Text)
    qty = Column(Numeric(14, 2))
    unit_rate = Column(Numeric(14, 2))
    raw_pr_category = Column(String(100))
    raw_lab_text = Column(String(150))
    amount_gst = Column(Numeric(14, 2))
    # "Suggested" = classifier's guess. May be overwritten by Team Lead correction.
    suggested_lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    suggested_lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    suggested_category_id = Column(BigInteger, ForeignKey("spending_categories.category_id"))
    classification_status = Column(String(30), nullable=False, default="pending")
    duplicate_status = Column(String(30), nullable=False, default="unchecked")
    review_status = Column(String(30), nullable=False, default="not_required")
    match_confidence = Column(Numeric(5, 2))
    match_reason = Column(Text)
    raw_line_json = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    header = relationship("StagingPRHeader", back_populates="lines")
    queue_item = relationship("ReviewQueueItem", back_populates="line", uselist=False, cascade="all, delete-orphan")


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    review_queue_id = Column(BigInteger, primary_key=True)
    staging_line_id = Column(BigInteger, ForeignKey("staging_pr_lines.staging_line_id"), nullable=False)
    assigned_to_user_id = Column(BigInteger, ForeignKey("users.user_id"))
    queue_status = Column(String(30), nullable=False, default="open")
    priority = Column(String(20), nullable=False, default="normal")
    review_reason = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    resolved_at = Column(DateTime(timezone=True))

    line = relationship("StagingPRLine", back_populates="queue_item")
    assignee = relationship("User")
