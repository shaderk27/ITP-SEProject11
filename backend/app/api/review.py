"""
Review queue API endpoints (W9-01).

Endpoints for Team Leads and Admins to see batches with unresolved
auto-classifications. Frontend's Review Queue page reads from here.
"""
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.staging import (
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
    UploadBatch,
)
from app.models.user import User

router = APIRouter(prefix="/api/review", tags=["Review"])

# Lab IC users cannot see the review queue per team spec.
ALLOWED_REVIEW_ROLES = {"admin", "teamlead"}


# ─── Response shape ──────────────────────────────────────────────────────
class BatchSummary(BaseModel):
    """One row in the Review Queue page's batch list."""
    batch_id: int
    filename: str
    upload_status: str
    uploaded_at: datetime
    uploader_name: str
    total_lines: int
    open_queue_count: int


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/batches", response_model=list[BatchSummary])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BatchSummary]:
    """
    Return batches that still have open review queue items.

    Role scoping:
      - Admin     → sees every batch with open items.
      - Team Lead → sees only batches that have at least one line tied
                    to their lab_group_id.
      - Lab IC    → 403.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view the review queue.",
        )

    # Find which batches still have at least one open queue item
    # (and, for Team Lead, at least one line in their lab_group).
    open_batches_query = (
        db.query(UploadBatch.batch_id)
        .join(StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id)
        .join(StagingPRLine, StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id)
        .join(ReviewQueueItem, ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id)
        .filter(ReviewQueueItem.queue_status == "open")
    )

    if role_name == "teamlead":
        if not current_user.lab_group_id:
            # Team Lead with no assigned group sees nothing — return empty list.
            return []
        open_batches_query = open_batches_query.filter(
            StagingPRLine.suggested_lab_group_id == current_user.lab_group_id
        )

    open_batch_ids = {row[0] for row in open_batches_query.distinct().all()}
    if not open_batch_ids:
        return []

    # Hydrate the full batch rows, newest first.
    batches = (
        db.query(UploadBatch)
        .filter(UploadBatch.batch_id.in_(open_batch_ids))
        .order_by(UploadBatch.uploaded_at.desc())
        .all()
    )

    return [
        _build_summary(db, batch, role_name, current_user.lab_group_id)
        for batch in batches
    ]


# ─── Helpers ─────────────────────────────────────────────────────────────
def _role_name(user: User) -> str:
    """Pull the user's role_name lowercased — empty string if unset."""
    return (user.role.role_name if user.role else "").lower().strip()


def _build_summary(
    db: Session,
    batch: UploadBatch,
    role_name: str,
    user_lab_group_id: int | None,
) -> BatchSummary:
    """Compute total_lines and open_queue_count for one batch, with role-aware filtering."""
    # Total parsed lines in this batch (not role-filtered — count what was uploaded).
    total_lines = (
        db.query(func.count(StagingPRLine.staging_line_id))
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .scalar()
        or 0
    )

    # Open queue items in this batch — Team Lead only sees their own group's items.
    open_count_query = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .filter(ReviewQueueItem.queue_status == "open")
    )
    if role_name == "teamlead" and user_lab_group_id is not None:
        open_count_query = open_count_query.filter(
            StagingPRLine.suggested_lab_group_id == user_lab_group_id
        )
    open_count = open_count_query.scalar() or 0

    return BatchSummary(
        batch_id=batch.batch_id,
        filename=batch.filename,
        upload_status=batch.upload_status,
        uploaded_at=batch.uploaded_at,
        uploader_name=batch.uploader.full_name if batch.uploader else "Unknown",
        total_lines=total_lines,
        open_queue_count=open_count,
    )
