"""
Review queue API endpoints (W9-01).

Endpoints for Team Leads and Admins to see batches with unresolved
auto-classifications. Frontend's Review Queue page reads from here.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.services.threshold_service import (
    check_and_notify_lab_thresholds,
    check_and_notify_lab_group_thresholds,
)
from app.services.knowledge_service import index_pr_lines_in_background
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
    amount_gst: str  # Decimal serialized as string for safe transport
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
    lab_code: str | None
    lab_name: str
    lab_group_id: int | None
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
    prs_updated: int
    lines_created: int
    pr_ids: list[int]


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/batches", response_model=list[BatchSummary])
def list_batches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[BatchSummary]:
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view the review queue.",
        )

    if role_name == "teamlead" and not current_user.lab_group_id:
        return []

    open_batches_query = (
        db.query(UploadBatch.batch_id)
        .join(StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id)
        .join(
            StagingPRLine,
            StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id,
        )
        .join(
            ReviewQueueItem,
            ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id,
        )
        .filter(ReviewQueueItem.queue_status == "open")
    )
    if role_name == "teamlead":
        open_batches_query = open_batches_query.filter(
            StagingPRLine.suggested_lab_group_id == current_user.lab_group_id
        )

    ready_batches_query = db.query(UploadBatch.batch_id).filter(
        UploadBatch.upload_status == "ready_to_commit"
    )
    if role_name == "teamlead":
        ready_batches_query = (
            ready_batches_query.join(
                StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id
            )
            .join(
                StagingPRLine,
                StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id,
            )
            .filter(StagingPRLine.suggested_lab_group_id == current_user.lab_group_id)
        )

    relevant_ids = {row[0] for row in open_batches_query.distinct().all()} | {
        row[0] for row in ready_batches_query.distinct().all()
    }
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

    lab_group_names = {
        g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()
    }
    lab_names = {lab.lab_id: lab.lab_name for lab in db.query(Lab).all()}
    category_names = {
        c.category_id: c.category_name for c in db.query(SpendingCategory).all()
    }

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
            .join(
                ReviewQueueItem,
                ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id,
            )
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .filter(ReviewQueueItem.queue_status.in_(["open", "resolved"]))
        )
        if role_name == "teamlead" and current_user.lab_group_id is not None:
            line_query = line_query.filter(
                StagingPRLine.suggested_lab_group_id == current_user.lab_group_id
            )

        line_rows = line_query.order_by(StagingPRLine.source_line_no).all()
        if not line_rows:
            continue

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
                    amount_gst=str(line.amount_gst)
                    if line.amount_gst is not None
                    else "0",
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
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Admin or Team Lead can resolve review items.",
        )

    item, line, header, batch = _load_queue_item_or_404(db, review_queue_id)

    if role_name == "teamlead":
        if (
            current_user.lab_group_id is None
            or line.suggested_lab_group_id != current_user.lab_group_id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This review item is not in your assigned lab group.",
            )

    lab_groups = db.query(LabGroup).order_by(LabGroup.lab_group_name).all()
    labs = db.query(Lab).order_by(Lab.lab_name).all()
    categories = (
        db.query(SpendingCategory).order_by(SpendingCategory.category_name).all()
    )
    lg_name_by_id = {g.lab_group_id: g.lab_group_name for g in lab_groups}
    lab_name_by_id = {lab.lab_id: lab.lab_name for lab in labs}
    cat_name_by_id = {c.category_id: c.category_name for c in categories}

    current_lab_group = lg_name_by_id.get(line.suggested_lab_group_id, "General")
    current_lab = lab_name_by_id.get(line.suggested_lab_id, "General")
    current_category = cat_name_by_id.get(line.suggested_category_id, "General")

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
                lab_id=lab.lab_id,
                lab_code=lab.lab_code,
                lab_name=lab.lab_name,
                lab_group_id=lab.lab_group_id,
                is_general=bool(lab.is_general),
            )
            for lab in labs
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
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Only Admin or Team Lead can resolve review items.",
        )

    item, line, header, batch = _load_queue_item_or_404(db, review_queue_id)

    if batch.upload_status == "committed":
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Batch {batch.batch_id} has already been committed. This item can no longer be edited.",
        )

    if role_name == "teamlead":
        if (
            current_user.lab_group_id is None
            or line.suggested_lab_group_id != current_user.lab_group_id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This review item is not in your assigned lab group.",
            )

    lab_group = (
        db.query(LabGroup).filter(LabGroup.lab_group_id == body.lab_group_id).first()
    )
    if not lab_group:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown lab_group_id={body.lab_group_id}."
        )
    lab = db.query(Lab).filter(Lab.lab_id == body.lab_id).first()
    if not lab:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown lab_id={body.lab_id}."
        )
    if lab.lab_group_id != body.lab_group_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Lab '{lab.lab_name}' does not belong to lab_group '{lab_group.lab_group_name}'.",
        )
    category = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == body.category_id)
        .first()
    )
    if not category:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown category_id={body.category_id}."
        )

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

    line.suggested_lab_group_id = body.lab_group_id
    line.suggested_lab_id = body.lab_id
    line.suggested_category_id = body.category_id
    line.review_status = "resolved"
    line.classification_status = "confident"

    item.queue_status = "resolved"
    item.resolved_at = func.now()

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

    remaining_open = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(
            StagingPRLine,
            StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id,
        )
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
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
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> CommitResponse:
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_REVIEW_ROLES:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN, "Only Admin or Team Lead can commit a batch."
        )

    batch = db.query(UploadBatch).filter(UploadBatch.batch_id == batch_id).first()
    if not batch:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Batch {batch_id} not found.")

    if batch.upload_status == "committed":
        raise HTTPException(
            status.HTTP_409_CONFLICT, f"Batch {batch_id} is already committed."
        )

    open_count = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(
            StagingPRLine,
            StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id,
        )
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
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

    if role_name == "teamlead":
        if current_user.lab_group_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Team Lead is not assigned to a lab group."
            )
        owns_any = (
            db.query(StagingPRLine.staging_line_id)
            .join(
                StagingPRHeader,
                StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
            )
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
    prs_created_count = 0
    prs_updated_count = 0
    lines_created = 0
    lines_updated = 0

    # Keep track of unique labs and lab groups affected by this commit
    affected_lab_ids = set()
    affected_lab_group_ids = set()

    for header in headers:
        lines = (
            db.query(StagingPRLine)
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .order_by(StagingPRLine.source_line_no)
            .all()
        )
        pr_lab_group_id = lines[0].suggested_lab_group_id if lines else None
        if pr_lab_group_id:
            affected_lab_group_ids.add(pr_lab_group_id)

        pr_status_value = _raw_line_value(lines[0], "pr_status") if lines else ""
        pr_status_value = pr_status_value or None

        existing_pr = (
            db.query(PurchaseRequest)
            .filter(PurchaseRequest.source_pr_number == header.source_pr_number)
            .first()
        )

        if existing_pr is None:
            change_type = "created"
            old_data = None

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
                pr_status=pr_status_value,
            )
            db.add(pr)
            db.flush()
            prs_created_count += 1
        else:
            change_type = "updated"
            existing_line_count = (
                db.query(func.count(PurchaseRequestLine.pr_line_id))
                .filter(PurchaseRequestLine.pr_id == existing_pr.pr_id)
                .scalar()
                or 0
            )
            old_data = {
                "source_pr_number": existing_pr.source_pr_number,
                "requestor_name": existing_pr.requestor_name,
                "wbs_code": existing_pr.wbs_code,
                "lab_group_id": existing_pr.lab_group_id,
                "grand_total_sgd": str(existing_pr.grand_total_sgd)
                if existing_pr.grand_total_sgd is not None
                else None,
                "line_count": existing_line_count,
                "latest_batch_id": existing_pr.latest_batch_id,
                "pr_status": existing_pr.pr_status,
            }

            existing_pr.latest_batch_id = batch.batch_id
            existing_pr.requestor_name = header.requestor_name
            existing_pr.req_type = header.req_type
            existing_pr.request_date = header.pr_sub_date
            existing_pr.purpose = header.purpose
            existing_pr.wbs_code = header.wbs_code
            existing_pr.instruction_to_vendor = header.instruction_to_vendor
            existing_pr.grand_total_sgd = header.grand_total_sgd
            existing_pr.lab_group_id = pr_lab_group_id
            existing_pr.pr_status = pr_status_value
            existing_pr.updated_at = func.now()
            db.flush()
            pr = existing_pr
            prs_updated_count += 1

        pr_ids.append(pr.pr_id)

        existing_lines_by_identity = _existing_committed_lines_by_identity(db, pr)
        status_updates: list[dict] = []

        for line in lines:
            if line.suggested_lab_id:
                affected_lab_ids.add(line.suggested_lab_id)
            if line.suggested_lab_group_id:
                affected_lab_group_ids.add(line.suggested_lab_group_id)

            line_identity_key = _raw_line_value(line, "line_identity_key")
            existing_line = existing_lines_by_identity.get(line_identity_key)
            if existing_line:
                old_staging_line = _staging_line_for_committed_line(db, existing_line)
                old_status = _source_status_snapshot(old_staging_line)
                new_status = _source_status_snapshot(line)

                existing_line.source_staging_line_id = line.staging_line_id
                existing_line.pr_status = _raw_line_value(line, "pr_status") or None
                lines_updated += 1
                if old_status != new_status:
                    status_updates.append(
                        {
                            "line_identity_key": line_identity_key,
                            "line_no": line.source_line_no,
                            "old_status": old_status,
                            "new_status": new_status,
                        }
                    )
                continue

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
                    pr_status=_raw_line_value(line, "pr_status") or None,
                )
            )
            lines_created += 1

        db.flush()
        final_line_count = (
            db.query(func.count(PurchaseRequestLine.pr_line_id))
            .filter(PurchaseRequestLine.pr_id == pr.pr_id)
            .scalar()
            or 0
        )
        new_data = {
            "source_pr_number": pr.source_pr_number,
            "requestor_name": pr.requestor_name,
            "wbs_code": pr.wbs_code,
            "lab_group_id": pr.lab_group_id,
            "grand_total_sgd": str(pr.grand_total_sgd)
            if pr.grand_total_sgd is not None
            else None,
            "line_count": final_line_count,
            "latest_batch_id": pr.latest_batch_id,
            "pr_status": pr.pr_status,
        }
        if status_updates:
            new_data["status_updates"] = [u["new_status"] for u in status_updates]
            if old_data is None:
                old_data = {}
            old_data["status_updates"] = [u["old_status"] for u in status_updates]

        db.add(
            PRVersion(
                pr_id=pr.pr_id,
                batch_id=batch.batch_id,
                change_type=change_type,
                old_data=old_data,
                new_data=new_data,
                changed_by=current_user.user_id,
                change_reason=f"Batch {batch.batch_id} committed",
            )
        )

    # Also ensure parent Lab Groups of any affected labs are included
    if affected_lab_ids:
        parent_group_rows = (
            db.query(Lab.lab_group_id)
            .filter(Lab.lab_id.in_(affected_lab_ids), Lab.lab_group_id.isnot(None))
            .distinct()
            .all()
        )
        for (gid,) in parent_group_rows:
            affected_lab_group_ids.add(gid)

    batch.upload_status = "committed"
    batch.processed_at = func.now()

    db.add(
        AuditLog(
            user_id=current_user.user_id,
            action_type="BATCH_COMMITTED",
            entity_name="upload_batches",
            record_id=str(batch.batch_id),
            old_value={"upload_status": "ready_to_commit"},
            new_value={
                "upload_status": "committed",
                "prs_created": prs_created_count,
                "prs_updated": prs_updated_count,
                "lines_created": lines_created,
                "lines_updated": lines_updated,
            },
        )
    )

    db.commit()

    # TRIGGER THRESHOLD EMAILS (Both Lab-level and Lab Group-level)
    for lab_id in affected_lab_ids:
        background_tasks.add_task(check_and_notify_lab_thresholds, lab_id)

    for group_id in affected_lab_group_ids:
        background_tasks.add_task(check_and_notify_lab_group_thresholds, group_id)

    # Refresh Ask AI's PR-line search cards (no-op when embeddings are off).
    if pr_ids:
        background_tasks.add_task(index_pr_lines_in_background, list(pr_ids))

    return CommitResponse(
        success=True,
        batch_id=batch.batch_id,
        new_upload_status=batch.upload_status,
        prs_created=prs_created_count,
        prs_updated=prs_updated_count,
        lines_created=lines_created,
        pr_ids=pr_ids,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────
def _load_queue_item_or_404(db: Session, review_queue_id: int):
    row = (
        db.query(ReviewQueueItem, StagingPRLine, StagingPRHeader, UploadBatch)
        .join(
            StagingPRLine,
            StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id,
        )
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
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
    return (user.role.role_name if user.role else "").lower().strip()


def _existing_committed_lines_by_identity(
    db: Session, pr: PurchaseRequest
) -> dict[str, PurchaseRequestLine]:
    lines_by_identity: dict[str, PurchaseRequestLine] = {}
    for line in pr.lines:
        staging_line = _staging_line_for_committed_line(db, line)
        line_identity_key = _raw_line_value(staging_line, "line_identity_key")
        if line_identity_key:
            lines_by_identity[line_identity_key] = line
    return lines_by_identity


def _staging_line_for_committed_line(
    db: Session, line: PurchaseRequestLine
) -> StagingPRLine | None:
    if line.source_staging_line_id is None:
        return None
    return (
        db.query(StagingPRLine)
        .filter(StagingPRLine.staging_line_id == line.source_staging_line_id)
        .first()
    )


def _raw_line_value(line: StagingPRLine | None, key: str) -> str:
    if line is None or not isinstance(line.raw_line_json, dict):
        return ""
    value = line.raw_line_json.get(key)
    return "" if value is None else str(value)


def _source_status_snapshot(line: StagingPRLine | None) -> dict[str, str]:
    return {
        "pr_status": _raw_line_value(line, "pr_status"),
        "po_number": _raw_line_value(line, "po_number"),
        "po_status": _raw_line_value(line, "po_status"),
    }


def _build_summary(
    db: Session,
    batch: UploadBatch,
    role_name: str,
    user_lab_group_id: int | None,
) -> BatchSummary:
    total_lines = (
        db.query(func.count(StagingPRLine.staging_line_id))
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .scalar()
        or 0
    )

    open_count_query = (
        db.query(func.count(ReviewQueueItem.review_queue_id))
        .join(
            StagingPRLine,
            StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id,
        )
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
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
