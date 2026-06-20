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
from app.models.config import Lab, LabGroup, SpendingCategory
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


# ─── Response shapes ─────────────────────────────────────────────────────
class BatchSummary(BaseModel):
    """One row in the Review Queue page's batch list."""
    batch_id: int
    filename: str
    upload_status: str
    uploaded_at: datetime
    uploader_name: str
    total_lines: int
    open_queue_count: int


class ReviewQueueLine(BaseModel):
    """One line error inside a PR group."""
    review_queue_id: int
    staging_line_id: int
    source_line_no: int | None
    item_details: str
    amount_gst: str          # Decimal serialized as string for safe transport
    wbs_code: str
    current_lab_group: str
    current_lab: str
    current_category: str
    is_lab_group_general: bool
    is_lab_general: bool
    is_category_general: bool
    review_reason: str
    queue_status: str


class ReviewPRGroup(BaseModel):
    """One PR header with its in-scope line errors."""
    source_pr_number: str
    requestor_name: str
    purpose: str
    wbs_code: str
    lines: list[ReviewQueueLine]


class BatchDetail(BaseModel):
    """Full batch view: header info + nested PRs and lines that need review."""
    batch_id: int
    filename: str
    upload_status: str
    uploaded_at: datetime
    uploader_name: str
    prs: list[ReviewPRGroup]


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


@router.get("/batches/{batch_id}", response_model=BatchDetail)
def get_batch_detail(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BatchDetail:
    """
    Return a single batch with its PRs and the line errors needing review.

    Role scoping mirrors /api/review/batches:
      - Admin sees every open line in the batch.
      - Team Lead sees only lines whose suggested_lab_group_id matches theirs.
      - Lab IC: 403.

    PRs that contain zero in-scope open lines are omitted from the response,
    so the page never shows empty PR groups.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view the review queue.",
        )

    batch = db.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Batch {batch_id} not found.",
        )

    # Name lookups so each line can carry resolved display strings.
    lab_group_names = {g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()}
    lab_names = {l.lab_id: l.lab_name for l in db.query(Lab).all()}
    category_names = {c.category_id: c.category_name for c in db.query(SpendingCategory).all()}

    headers = (
        db.query(StagingPRHeader)
        .filter(StagingPRHeader.batch_id == batch_id)
        .order_by(StagingPRHeader.source_pr_number)
        .all()
    )

    pr_groups: list[ReviewPRGroup] = []
    for header in headers:
        line_query = (
            db.query(StagingPRLine, ReviewQueueItem)
            .join(ReviewQueueItem, ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id)
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .filter(ReviewQueueItem.queue_status == "open")
        )
        if role_name == "teamlead" and current_user.lab_group_id is not None:
            line_query = line_query.filter(
                StagingPRLine.suggested_lab_group_id == current_user.lab_group_id
            )

        line_rows = line_query.order_by(StagingPRLine.source_line_no).all()
        if not line_rows:
            continue  # Skip PRs with no in-scope open lines.

        lines: list[ReviewQueueLine] = []
        for line, queue_item in line_rows:
            lg_name = lab_group_names.get(line.suggested_lab_group_id, "General")
            lab_name = lab_names.get(line.suggested_lab_id, "General")
            cat_name = category_names.get(line.suggested_category_id, "General")
            lines.append(
                ReviewQueueLine(
                    review_queue_id=queue_item.review_queue_id,
                    staging_line_id=line.staging_line_id,
                    source_line_no=line.source_line_no,
                    item_details=line.item_details or "",
                    amount_gst=str(line.amount_gst) if line.amount_gst is not None else "0",
                    wbs_code=header.wbs_code or "",
                    current_lab_group=lg_name,
                    current_lab=lab_name,
                    current_category=cat_name,
                    is_lab_group_general=lg_name.lower() == "general",
                    is_lab_general=lab_name.lower() == "general",
                    is_category_general=cat_name.lower() == "general",
                    review_reason=queue_item.review_reason or "",
                    queue_status=queue_item.queue_status,
                )
            )

        pr_groups.append(
            ReviewPRGroup(
                source_pr_number=header.source_pr_number,
                requestor_name=header.requestor_name or "",
                purpose=header.purpose or "",
                wbs_code=header.wbs_code or "",
                lines=lines,
            )
        )

    return BatchDetail(
        batch_id=batch.batch_id,
        filename=batch.filename,
        upload_status=batch.upload_status,
        uploaded_at=batch.uploaded_at,
        uploader_name=batch.uploader.full_name if batch.uploader else "Unknown",
        prs=pr_groups,
    )


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
