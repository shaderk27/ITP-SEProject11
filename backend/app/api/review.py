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
    AuditLog,
    PRVersion,
    PurchaseRequest,
    PurchaseRequestLine,
    ReviewAction,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
    UploadBatch,
)
from app.models.auth import User

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


# ─── Detail / correction shapes ──────────────────────────────────────────
class LabGroupOption(BaseModel):
    lab_group_id: int
    lab_group_name: str
    wbs_code: str


class LabOption(BaseModel):
    lab_id: int
    lab_name: str
    lab_group_id: int
    is_general: bool


class CategoryOption(BaseModel):
    category_id: int
    category_name: str


class LastReviewAction(BaseModel):
    """Most recent correction on a queue item (for the 'last corrected by' footer)."""
    reviewer_name: str
    reviewed_at: datetime
    comment: str | None
    action_type: str


class QueueItemDetail(BaseModel):
    """Everything the Edit Line form needs to render in one payload."""
    # Queue identity / state
    review_queue_id: int
    queue_status: str
    review_reason: str
    # Batch context (so the form knows when to lock — only locks after commit).
    batch_upload_status: str
    # Most recent correction (None if never edited). Drives the footer.
    last_action: LastReviewAction | None
    # Line data
    staging_line_id: int
    source_line_no: int | None
    item_details: str
    amount_gst: str
    qty: str | None
    unit_rate: str | None
    raw_pr_category: str | None
    # PR header context
    source_pr_number: str
    requestor_name: str
    purpose: str
    wbs_code: str
    instruction_to_vendor: str
    pr_sub_date: str | None
    # Batch context
    batch_id: int
    batch_filename: str
    # Current classification (the classifier's guess or last correction)
    suggested_lab_group_id: int | None
    suggested_lab_id: int | None
    suggested_category_id: int | None
    current_lab_group: str
    current_lab: str
    current_category: str
    is_lab_group_general: bool
    is_lab_general: bool
    is_category_general: bool
    # Dropdown options for the form
    available_lab_groups: list[LabGroupOption]
    available_labs: list[LabOption]
    available_categories: list[CategoryOption]


class CorrectionRequest(BaseModel):
    lab_group_id: int
    lab_id: int
    category_id: int
    comment: str | None = None


class CorrectionResponse(BaseModel):
    success: bool
    review_queue_id: int
    new_queue_status: str
    batch_remaining_open: int


class CommitResponse(BaseModel):
    success: bool
    batch_id: int
    new_upload_status: str
    prs_created: int
    lines_created: int
    pr_ids: list[int]


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/batches", response_model=list[BatchSummary])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BatchSummary]:
    """
    Return batches relevant to the Review Queue page:
      - batches that still have at least one OPEN queue item, OR
      - batches in 'ready_to_commit' status (waiting for the commit click).

    Role scoping:
      - Admin     → sees every relevant batch.
      - Team Lead → only batches that have at least one line in their lab_group.
      - Lab IC    → 403.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view the review queue.",
        )

    if role_name == "teamlead" and not current_user.lab_group_id:
        return []

    # 1. Batches with at least one open queue item (active review work).
    open_batches_query = (
        db.query(UploadBatch.batch_id)
        .join(StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id)
        .join(StagingPRLine, StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id)
        .join(ReviewQueueItem, ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id)
        .filter(ReviewQueueItem.queue_status == "open")
    )
    if role_name == "teamlead":
        open_batches_query = open_batches_query.filter(
            StagingPRLine.suggested_lab_group_id == current_user.lab_group_id
        )

    # 2. Batches in 'ready_to_commit' status (zero open items, awaiting Commit click).
    ready_batches_query = (
        db.query(UploadBatch.batch_id)
        .filter(UploadBatch.upload_status == "ready_to_commit")
    )
    if role_name == "teamlead":
        ready_batches_query = (
            ready_batches_query
            .join(StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id)
            .join(StagingPRLine, StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id)
            .filter(StagingPRLine.suggested_lab_group_id == current_user.lab_group_id)
        )

    relevant_ids = (
        {row[0] for row in open_batches_query.distinct().all()}
        | {row[0] for row in ready_batches_query.distinct().all()}
    )
    if not relevant_ids:
        return []

    batches = (
        db.query(UploadBatch)
        .filter(UploadBatch.batch_id.in_(relevant_ids))
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
        # Include both 'open' and 'resolved' queue items so Team Leads can
        # re-edit a saved correction before the batch is committed.
        line_query = (
            db.query(StagingPRLine, ReviewQueueItem)
            .join(ReviewQueueItem, ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id)
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .filter(ReviewQueueItem.queue_status.in_(["open", "resolved"]))
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


@router.get("/queue/{review_queue_id}", response_model=QueueItemDetail)
def get_queue_item(
    review_queue_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> QueueItemDetail:
    """
    Single queue item view for the Edit Line form. Returns everything the
    UI needs in one payload, including dropdown options.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admin or Team Lead can resolve review items.")

    item, line, header, batch = _load_queue_item_or_404(db, review_queue_id)

    # Team Lead can only see items in their own lab_group.
    if role_name == "teamlead":
        if current_user.lab_group_id is None or line.suggested_lab_group_id != current_user.lab_group_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This review item is not in your assigned lab group.",
            )

    # Resolve current display names.
    lab_groups = db.query(LabGroup).order_by(LabGroup.lab_group_name).all()
    labs = db.query(Lab).order_by(Lab.lab_name).all()
    categories = db.query(SpendingCategory).order_by(SpendingCategory.category_name).all()
    lg_name_by_id = {g.lab_group_id: g.lab_group_name for g in lab_groups}
    lab_name_by_id = {l.lab_id: l.lab_name for l in labs}
    cat_name_by_id = {c.category_id: c.category_name for c in categories}

    current_lab_group = lg_name_by_id.get(line.suggested_lab_group_id, "General")
    current_lab = lab_name_by_id.get(line.suggested_lab_id, "General")
    current_category = cat_name_by_id.get(line.suggested_category_id, "General")

    # Pull the most recent review_action on this queue item, if any.
    latest_action_row = (
        db.query(ReviewAction, User)
        .join(User, User.user_id == ReviewAction.reviewed_by)
        .filter(ReviewAction.review_queue_id == item.review_queue_id)
        .order_by(ReviewAction.reviewed_at.desc())
        .first()
    )
    last_action: LastReviewAction | None = None
    if latest_action_row:
        action, reviewer = latest_action_row
        last_action = LastReviewAction(
            reviewer_name=reviewer.full_name,
            reviewed_at=action.reviewed_at,
            comment=action.review_comment,
            action_type=action.action_type,
        )

    return QueueItemDetail(
        review_queue_id=item.review_queue_id,
        queue_status=item.queue_status,
        review_reason=item.review_reason or "",
        batch_upload_status=batch.upload_status,
        last_action=last_action,
        staging_line_id=line.staging_line_id,
        source_line_no=line.source_line_no,
        item_details=line.item_details or "",
        amount_gst=str(line.amount_gst) if line.amount_gst is not None else "0",
        qty=str(line.qty) if line.qty is not None else None,
        unit_rate=str(line.unit_rate) if line.unit_rate is not None else None,
        raw_pr_category=line.raw_pr_category,
        source_pr_number=header.source_pr_number,
        requestor_name=header.requestor_name or "",
        purpose=header.purpose or "",
        wbs_code=header.wbs_code or "",
        instruction_to_vendor=header.instruction_to_vendor or "",
        pr_sub_date=header.pr_sub_date.isoformat() if header.pr_sub_date else None,
        batch_id=batch.batch_id,
        batch_filename=batch.filename,
        suggested_lab_group_id=line.suggested_lab_group_id,
        suggested_lab_id=line.suggested_lab_id,
        suggested_category_id=line.suggested_category_id,
        current_lab_group=current_lab_group,
        current_lab=current_lab,
        current_category=current_category,
        is_lab_group_general=current_lab_group.lower() == "general",
        is_lab_general=current_lab.lower() == "general",
        is_category_general=current_category.lower() == "general",
        available_lab_groups=[
            LabGroupOption(
                lab_group_id=g.lab_group_id,
                lab_group_name=g.lab_group_name,
                wbs_code=g.wbs_code or "",
            )
            for g in lab_groups
        ],
        available_labs=[
            LabOption(
                lab_id=l.lab_id,
                lab_name=l.lab_name,
                lab_group_id=l.lab_group_id,
                is_general=bool(l.is_general),
            )
            for l in labs
        ],
        available_categories=[
            CategoryOption(category_id=c.category_id, category_name=c.category_name)
            for c in categories
        ],
    )


@router.post("/queue/{review_queue_id}/correct", response_model=CorrectionResponse)
def correct_queue_item(
    review_queue_id: int,
    body: CorrectionRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CorrectionResponse:
    """
    Apply a manual correction to one queue item.

    Side effects (single transaction):
      - Update staging_pr_lines.suggested_* with picked IDs
      - Mark staging_pr_lines.review_status = 'resolved'
      - Mark review_queue_items.queue_status = 'resolved' + resolved_at
      - Insert review_actions row (per-correction audit)
      - Insert audit_logs row (system-wide audit, W11-04 plumbing)
      - If batch now has zero open items, upgrade upload_batches.upload_status
        to 'ready_to_commit'.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admin or Team Lead can resolve review items.")

    item, line, header, batch = _load_queue_item_or_404(db, review_queue_id)

    # Block edits only after the batch has been committed to final tables.
    # Before commit: Team Leads can re-correct the same item as many times
    # as they need to (each save adds a new review_actions row, full history).
    if batch.upload_status == "committed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {batch.batch_id} has already been committed. This item can no longer be edited.",
        )

    # Team Lead scoping: must own the item's current lab_group.
    if role_name == "teamlead":
        if current_user.lab_group_id is None or line.suggested_lab_group_id != current_user.lab_group_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This review item is not in your assigned lab group.",
            )

    # Validate FKs exist + lab belongs to chosen group.
    lab_group = db.query(LabGroup).filter(LabGroup.lab_group_id == body.lab_group_id).first()
    if not lab_group:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown lab_group_id={body.lab_group_id}.")
    lab = db.query(Lab).filter(Lab.lab_id == body.lab_id).first()
    if not lab:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown lab_id={body.lab_id}.")
    if lab.lab_group_id != body.lab_group_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Lab '{lab.lab_name}' does not belong to lab_group '{lab_group.lab_group_name}'.",
        )
    category = db.query(SpendingCategory).filter(SpendingCategory.category_id == body.category_id).first()
    if not category:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown category_id={body.category_id}.")

    # Snapshot old values for audit before mutating.
    old_values = {
        "suggested_lab_group_id": line.suggested_lab_group_id,
        "suggested_lab_id": line.suggested_lab_id,
        "suggested_category_id": line.suggested_category_id,
        "review_status": line.review_status,
    }
    new_values = {
        "suggested_lab_group_id": body.lab_group_id,
        "suggested_lab_id": body.lab_id,
        "suggested_category_id": body.category_id,
        "review_status": "resolved",
    }

    # 1. Update the staging line with the corrected classification.
    line.suggested_lab_group_id = body.lab_group_id
    line.suggested_lab_id = body.lab_id
    line.suggested_category_id = body.category_id
    line.review_status = "resolved"
    line.classification_status = "confident"

    # 2. Close the queue item.
    item.queue_status = "resolved"
    item.resolved_at = func.now()

    # 3. Write per-correction audit row.
    db.add(
        ReviewAction(
            review_queue_id=item.review_queue_id,
            reviewed_by=current_user.user_id,
            final_lab_group_id=body.lab_group_id,
            final_lab_id=body.lab_id,
            final_category_id=body.category_id,
            action_type="corrected",
            review_comment=body.comment,
        )
    )

    # 4. Write system-wide audit row.
    db.add(
        AuditLog(
            user_id=current_user.user_id,
            action_type="REVIEW_RESOLVED",
            entity_name="review_queue_items",
            record_id=str(item.review_queue_id),
            old_value=old_values,
            new_value=new_values,
        )
    )

    db.flush()

    # 5. If this was the last open item in the batch, mark batch ready_to_commit.
    remaining_open = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .filter(ReviewQueueItem.queue_status == "open")
        .scalar()
        or 0
    )
    if remaining_open == 0 and batch.upload_status == "review_pending":
        batch.upload_status = "ready_to_commit"

    db.commit()

    return CorrectionResponse(
        success=True,
        review_queue_id=item.review_queue_id,
        new_queue_status=item.queue_status,
        batch_remaining_open=remaining_open,
    )


@router.post("/batches/{batch_id}/commit", response_model=CommitResponse)
def commit_batch(
    batch_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommitResponse:
    """
    Promote a fully-reviewed batch from staging into the final tables (W9-02).

    Preconditions:
      - User is Admin or Team Lead.
      - Batch must exist.
      - Batch must have NO open review_queue_items (every line resolved).
      - For Team Lead: batch must contain at least one line in their lab_group.

    Side effects (single transaction):
      - INSERT one purchase_requests row per staging_pr_headers row
      - INSERT one purchase_request_lines row per staging_pr_lines row
        (carrying source_staging_line_id for traceability)
      - INSERT one pr_versions row per PR (change_type='created')
      - UPDATE upload_batches.upload_status = 'committed', processed_at = NOW()
      - INSERT one audit_logs row (BATCH_COMMITTED)
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only Admin or Team Lead can commit a batch.")

    batch = db.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Batch {batch_id} not found.")

    # Block re-commits.
    if batch.upload_status == "committed":
        raise HTTPException(status.HTTP_409_CONFLICT, f"Batch {batch_id} is already committed.")

    # Block if any open queue items remain.
    open_count = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch_id)
        .filter(ReviewQueueItem.queue_status == "open")
        .scalar()
        or 0
    )
    if open_count > 0:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {batch_id} still has {open_count} open review item(s). Resolve them first.",
        )

    # Team Lead scope: must own at least one line in this batch.
    if role_name == "teamlead":
        if current_user.lab_group_id is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Team Lead is not assigned to a lab group.")
        owns_any = (
            db.query(StagingPRLine.staging_line_id)
            .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
            .filter(StagingPRHeader.batch_id == batch_id)
            .filter(StagingPRLine.suggested_lab_group_id == current_user.lab_group_id)
            .first()
        )
        if not owns_any:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This batch has no lines in your assigned lab group.",
            )

    headers = (
        db.query(StagingPRHeader)
        .filter(StagingPRHeader.batch_id == batch_id)
        .order_by(StagingPRHeader.source_pr_number)
        .all()
    )
    if not headers:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {batch_id} has no staging headers to commit.",
        )

    pr_ids: list[int] = []
    lines_created = 0

    for header in headers:
        lines = (
            db.query(StagingPRLine)
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .order_by(StagingPRLine.source_line_no)
            .all()
        )
        # Use the first line's lab_group as the PR-level lab_group_id.
        # (All lines under one PR typically share a group; refine later if not.)
        pr_lab_group_id = lines[0].suggested_lab_group_id if lines else None

        pr = PurchaseRequest(
            source_pr_number=header.source_pr_number,
            latest_batch_id=batch.batch_id,
            requestor_name=header.requestor_name,
            req_type=header.req_type,
            request_date=header.pr_sub_date,
            purpose=header.purpose,
            wbs_code=header.wbs_code,
            instruction_to_vendor=header.instruction_to_vendor,
            grand_total_sgd=header.grand_total_sgd,
            lab_group_id=pr_lab_group_id,
        )
        db.add(pr)
        db.flush()
        pr_ids.append(pr.pr_id)

        for line in lines:
            db.add(
                PurchaseRequestLine(
                    pr_id=pr.pr_id,
                    line_no=line.source_line_no,
                    item_description=line.item_details,
                    qty=line.qty,
                    unit_rate=line.unit_rate,
                    amount_gst=line.amount_gst if line.amount_gst is not None else 0,
                    currency_code="SGD",
                    lab_id=line.suggested_lab_id,
                    category_id=line.suggested_category_id,
                    source_staging_line_id=line.staging_line_id,
                )
            )
            lines_created += 1

        # History row for this PR.
        db.add(
            PRVersion(
                pr_id=pr.pr_id,
                batch_id=batch.batch_id,
                change_type="created",
                old_data=None,
                new_data={
                    "source_pr_number": pr.source_pr_number,
                    "requestor_name": pr.requestor_name,
                    "wbs_code": pr.wbs_code,
                    "lab_group_id": pr.lab_group_id,
                    "grand_total_sgd": str(pr.grand_total_sgd) if pr.grand_total_sgd is not None else None,
                    "line_count": len(lines),
                },
                changed_by=current_user.user_id,
                change_reason=f"Batch {batch.batch_id} committed",
            )
        )

    # Mark batch committed.
    batch.upload_status = "committed"
    batch.processed_at = func.now()

    # System audit.
    db.add(
        AuditLog(
            user_id=current_user.user_id,
            action_type="BATCH_COMMITTED",
            entity_name="upload_batches",
            record_id=str(batch.batch_id),
            old_value={"upload_status": "ready_to_commit"},
            new_value={
                "upload_status": "committed",
                "prs_created": len(pr_ids),
                "lines_created": lines_created,
            },
        )
    )

    db.commit()

    return CommitResponse(
        success=True,
        batch_id=batch.batch_id,
        new_upload_status=batch.upload_status,
        prs_created=len(pr_ids),
        lines_created=lines_created,
        pr_ids=pr_ids,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────
def _load_queue_item_or_404(db: Session, review_queue_id: int):
    """Fetch a queue item joined with line / header / batch, or raise 404."""
    row = (
        db.query(ReviewQueueItem, StagingPRLine, StagingPRHeader, UploadBatch)
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .join(UploadBatch, UploadBatch.batch_id == StagingPRHeader.batch_id)
        .filter(ReviewQueueItem.review_queue_id == review_queue_id)
        .first()
    )
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Review queue item {review_queue_id} not found.",
        )
    return row


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
