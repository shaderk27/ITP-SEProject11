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
from sqlalchemy.dialects.postgresql import INET, JSONB
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
    uploaded_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    processed_at = Column(DateTime(timezone=True))

    uploader = relationship("User")
    headers = relationship(
        "StagingPRHeader", back_populates="batch", cascade="all, delete-orphan"
    )


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
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    batch = relationship("UploadBatch", back_populates="headers")
    lines = relationship(
        "StagingPRLine", back_populates="header", cascade="all, delete-orphan"
    )


class StagingPRLine(Base):
    __tablename__ = "staging_pr_lines"

    staging_line_id = Column(BigInteger, primary_key=True)
    staging_header_id = Column(
        BigInteger, ForeignKey("staging_pr_headers.staging_header_id"), nullable=False
    )
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
    suggested_category_id = Column(
        BigInteger, ForeignKey("spending_categories.category_id")
    )
    classification_status = Column(String(30), nullable=False, default="pending")
    duplicate_status = Column(String(30), nullable=False, default="unchecked")
    review_status = Column(String(30), nullable=False, default="not_required")
    match_confidence = Column(Numeric(5, 2))
    match_reason = Column(Text)
    raw_line_json = Column(JSONB)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    header = relationship("StagingPRHeader", back_populates="lines")
    queue_item = relationship(
        "ReviewQueueItem",
        back_populates="line",
        uselist=False,
        cascade="all, delete-orphan",
    )


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"

    review_queue_id = Column(BigInteger, primary_key=True)
    staging_line_id = Column(
        BigInteger, ForeignKey("staging_pr_lines.staging_line_id"), nullable=False
    )
    assigned_to_user_id = Column(BigInteger, ForeignKey("users.user_id"))
    queue_status = Column(String(30), nullable=False, default="open")
    priority = Column(String(20), nullable=False, default="normal")
    review_reason = Column(Text)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    resolved_at = Column(DateTime(timezone=True))

    line = relationship("StagingPRLine", back_populates="queue_item")
    assignee = relationship("User")
    actions = relationship(
        "ReviewAction", back_populates="queue_item", cascade="all, delete-orphan"
    )


class ReviewAction(Base):
    """One row per correction/action a reviewer takes on a queue item."""

    __tablename__ = "review_actions"

    review_action_id = Column(BigInteger, primary_key=True)
    review_queue_id = Column(
        BigInteger, ForeignKey("review_queue_items.review_queue_id"), nullable=False
    )
    reviewed_by = Column(BigInteger, ForeignKey("users.user_id"), nullable=False)
    final_lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    final_lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    final_category_id = Column(
        BigInteger, ForeignKey("spending_categories.category_id")
    )
    # action_type examples: 'corrected', 'approved', 'rejected'
    action_type = Column(String(30), nullable=False)
    review_comment = Column(Text)
    reviewed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    queue_item = relationship("ReviewQueueItem", back_populates="actions")
    reviewer = relationship("User")


class AuditLog(Base):
    """System-wide audit trail (W11-04 plumbing)."""

    __tablename__ = "audit_logs"

    audit_id = Column(BigInteger, primary_key=True)
    user_id = Column(BigInteger, ForeignKey("users.user_id"))
    action_type = Column(String(50), nullable=False)
    entity_name = Column(String(100), nullable=False)
    record_id = Column(String(100), nullable=False)
    old_value = Column(JSONB)
    new_value = Column(JSONB)
    ip_address = Column(INET)
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    user = relationship("User")


# ─── Final tables (post-commit) ───────────────────────────────────────────
class PurchaseRequest(Base):
    """Finalized PR header. Populated when a batch is committed (W9-02)."""

    __tablename__ = "purchase_requests"

    pr_id = Column(BigInteger, primary_key=True)
    source_pr_number = Column(String(50), nullable=False)
    latest_batch_id = Column(BigInteger, ForeignKey("upload_batches.batch_id"))
    requestor_name = Column(String(150))
    req_type = Column(String(150))
    request_date = Column(Date)
    purpose = Column(Text)
    wbs_code = Column(String(100))
    instruction_to_vendor = Column(Text)
    grand_total_sgd = Column(Numeric(14, 2))
    lab_group_id = Column(BigInteger, ForeignKey("lab_groups.lab_group_id"))
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    lines = relationship(
        "PurchaseRequestLine",
        back_populates="purchase_request",
        cascade="all, delete-orphan",
    )
    versions = relationship(
        "PRVersion", back_populates="purchase_request", cascade="all, delete-orphan"
    )


class PurchaseRequestLine(Base):
    """Finalized PR line. One per committed staging_pr_line."""

    __tablename__ = "purchase_request_lines"

    pr_line_id = Column(BigInteger, primary_key=True)
    pr_id = Column(BigInteger, ForeignKey("purchase_requests.pr_id"), nullable=False)
    line_no = Column(Integer)
    item_description = Column(Text)
    qty = Column(Numeric(14, 2))
    unit_rate = Column(Numeric(14, 2))
    amount_gst = Column(Numeric(14, 2), nullable=False)
    currency_code = Column(String(10), nullable=False, default="SGD")
    lab_id = Column(BigInteger, ForeignKey("labs.lab_id"))
    category_id = Column(BigInteger, ForeignKey("spending_categories.category_id"))
    # Traceability back to the staging row this was promoted from.
    source_staging_line_id = Column(
        BigInteger, ForeignKey("staging_pr_lines.staging_line_id")
    )
    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    purchase_request = relationship("PurchaseRequest", back_populates="lines")


class PRVersion(Base):
    """Per-PR change history. Written on commit and on subsequent updates."""

    __tablename__ = "pr_versions"

    version_id = Column(BigInteger, primary_key=True)
    pr_id = Column(BigInteger, ForeignKey("purchase_requests.pr_id"), nullable=False)
    batch_id = Column(BigInteger, ForeignKey("upload_batches.batch_id"))
    # change_type examples: 'created', 'updated', 'recommitted'
    change_type = Column(String(30), nullable=False)
    old_data = Column(JSONB)
    new_data = Column(JSONB)
    changed_by = Column(BigInteger, ForeignKey("users.user_id"))
    change_reason = Column(Text)
    changed_at = Column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    purchase_request = relationship("PurchaseRequest", back_populates="versions")
    user = relationship("User")
