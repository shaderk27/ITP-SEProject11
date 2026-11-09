"""
Review queue API endpoints (W9-01).

Endpoints for Team Leads and Admins to see batches with unresolved
auto-classifications. Frontend's Review Queue page reads from here.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.services.threshold_service import (
    check_and_notify_lab_thresholds,
    check_and_notify_lab_group_thresholds,
)
from app.services.knowledge_service import index_pr_lines_in_background
from app.services.duplicate_service import is_status_regression
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
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


class WBSAllocationItem(BaseModel):
    """One WBS allocation portion inside a multi-WBS purchase line."""

    allocation_index: int
    row_number: int | None = None
    wbs_code: str
    mca: str | None = None
    amount_gst: str | None = None
    amount_missing: bool = False
    suggested_lab_group_id: int | None = None
    suggested_lab_id: int | None = None
    suggested_category_id: int | None = None
    current_lab_group: str = "General"
    current_lab: str = "General"
    current_category: str = "General"
    is_lab_group_general: bool = True
    is_lab_general: bool = True
    is_category_general: bool = True


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
    wbs_allocations: list[WBSAllocationItem] = []
    allocations_reconciled: bool = True
    allocated_total_gst: str | None = None


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
    # Multi-WBS allocations (empty for ordinary single-WBS lines)
    wbs_allocations: list[WBSAllocationItem] = []
    allocations_reconciled: bool = True
    allocated_total_gst: str | None = None
    # Dropdown options for the form
    available_lab_groups: list[LabGroupOption]
    available_labs: list[LabOption]
    available_categories: list[CategoryOption]


class AllocationCorrectionItem(BaseModel):
    wbs_code: str
    amount_gst: Decimal
    lab_group_id: int
    lab_id: int
    category_id: int


class CorrectionRequest(BaseModel):
    lab_group_id: int | None = None
    lab_id: int | None = None
    category_id: int | None = None
    comment: str | None = None
    allocations: list[AllocationCorrectionItem] | None = None


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
    status_regressions_skipped: int = 0


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

    open_rows = (
        db.query(UploadBatch.batch_id, StagingPRLine)
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
        .all()
    )
    open_batch_ids = {
        b_id
        for b_id, s_line in open_rows
        if role_name != "teamlead"
        or _line_in_teamlead_scope(s_line, current_user.lab_group_id)
    }

    ready_rows = (
        db.query(UploadBatch.batch_id, StagingPRLine)
        .join(StagingPRHeader, StagingPRHeader.batch_id == UploadBatch.batch_id)
        .join(
            StagingPRLine,
            StagingPRLine.staging_header_id == StagingPRHeader.staging_header_id,
        )
        .filter(UploadBatch.upload_status == "ready_to_commit")
        .all()
    )
    ready_batch_ids = {
        b_id
        for b_id, s_line in ready_rows
        if role_name != "teamlead"
        or _line_in_teamlead_scope(s_line, current_user.lab_group_id)
    }

    relevant_ids = open_batch_ids | ready_batch_ids
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
        line_rows = (
            db.query(StagingPRLine, ReviewQueueItem)
            .join(
                ReviewQueueItem,
                ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id,
            )
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .filter(ReviewQueueItem.queue_status.in_(["open", "resolved"]))
            .order_by(StagingPRLine.source_line_no)
            .all()
        )
        if role_name == "teamlead" and current_user.lab_group_id is not None:
            line_rows = [
                (s_line, q_item)
                for s_line, q_item in line_rows
                if _line_in_teamlead_scope(s_line, current_user.lab_group_id)
            ]
        if not line_rows:
            continue

        lines: list[ReviewQueueLine] = []
        for line, queue_item in line_rows:
            lg_name = lab_group_names.get(line.suggested_lab_group_id, "General")
            lab_name = lab_names.get(line.suggested_lab_id, "General")
            cat_name = category_names.get(line.suggested_category_id, "General")
            alloc_items, reconciles, alloc_total_str = _build_wbs_allocation_items(
                line, lab_group_names, lab_names, category_names
            )
            display_wbs = (
                ", ".join(dict.fromkeys(a.wbs_code for a in alloc_items if a.wbs_code))
                if alloc_items
                else (_raw_line_value(line, "wbs") or header.wbs_code or "")
            )
            lines.append(
                ReviewQueueLine(
                    review_queue_id=queue_item.review_queue_id,
                    staging_line_id=line.staging_line_id,
                    source_line_no=line.source_line_no,
                    item_details=line.item_details or "",
                    amount_gst=str(line.amount_gst)
                    if line.amount_gst is not None
                    else "0",
                    wbs_code=display_wbs,
                    current_lab_group=lg_name,
                    current_lab=lab_name,
                    current_category=cat_name,
                    is_lab_group_general=lg_name.lower() == "general",
                    is_lab_general=lab_name.lower() == "general",
                    is_category_general=cat_name.lower() == "general",
                    review_reason=queue_item.review_reason or "",
                    queue_status=queue_item.queue_status,
                    wbs_allocations=alloc_items,
                    allocations_reconciled=reconciles,
                    allocated_total_gst=alloc_total_str,
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
        if current_user.lab_group_id is None or not _line_in_teamlead_scope(
            line, current_user.lab_group_id
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

    # Restrict selectable Lab Groups and Labs to the Team Lead's permitted budget scope
    if role_name == "teamlead" and current_user.lab_group_id is not None:
        scoped_lab_groups = [
            g for g in lab_groups if g.lab_group_id == current_user.lab_group_id
        ]
        scoped_labs = [
            lab for lab in labs if lab.lab_group_id == current_user.lab_group_id
        ]
    else:
        scoped_lab_groups = lab_groups
        scoped_labs = labs

    current_lab_group = lg_name_by_id.get(line.suggested_lab_group_id, "General")
    current_lab = lab_name_by_id.get(line.suggested_lab_id, "General")
    current_category = cat_name_by_id.get(line.suggested_category_id, "General")

    alloc_items, reconciles, alloc_total_str = _build_wbs_allocation_items(
        line, lg_name_by_id, lab_name_by_id, cat_name_by_id
    )
    display_wbs = (
        ", ".join(dict.fromkeys(a.wbs_code for a in alloc_items if a.wbs_code))
        if alloc_items
        else (_raw_line_value(line, "wbs") or header.wbs_code or "")
    )

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
        wbs_code=display_wbs,
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
        wbs_allocations=alloc_items,
        allocations_reconciled=reconciles,
        allocated_total_gst=alloc_total_str,
        available_lab_groups=[
            LabGroupOption(
                lab_group_id=g.lab_group_id,
                lab_group_name=g.lab_group_name,
                wbs_code=g.wbs_code or "",
            )
            for g in scoped_lab_groups
        ],
        available_labs=[
            LabOption(
                lab_id=lab.lab_id,
                lab_code=lab.lab_code,
                lab_name=lab.lab_name,
                lab_group_id=lab.lab_group_id,
                is_general=bool(lab.is_general),
            )
            for lab in scoped_labs
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
        if current_user.lab_group_id is None or not _line_in_teamlead_scope(
            line, current_user.lab_group_id
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This review item is not in your assigned lab group.",
            )

    raw_json = dict(line.raw_line_json) if isinstance(line.raw_line_json, dict) else {}
    existing_allocs = list(raw_json.get("wbs_allocations") or [])
    line_amount = Decimal(str(line.amount_gst or 0)).quantize(Decimal("0.01"))

    old_values: dict[str, Any] = {
        "suggested_lab_group_id": line.suggested_lab_group_id,
        "suggested_lab_id": line.suggested_lab_id,
        "suggested_category_id": line.suggested_category_id,
        "review_status": line.review_status,
    }
    if existing_allocs:
        old_values["wbs_allocations"] = existing_allocs

    # ─── Path A: Explicit Multi-WBS Allocation Confirmation / Correction ──
    if body.allocations is not None and len(body.allocations) > 0:
        validated_allocs: list[dict[str, Any]] = []
        alloc_sum = Decimal("0.00")
        parent_identity_key = str(
            raw_json.get("line_identity_key")
            or f"{header.source_pr_number}::{line.source_line_no}"
        )

        for idx, alloc_in in enumerate(body.allocations, start=1):
            if (
                role_name == "teamlead"
                and alloc_in.lab_group_id != current_user.lab_group_id
            ):
                raise HTTPException(
                    status.HTTP_403_FORBIDDEN,
                    "Team Leads can only assign allocations within their own assigned Lab Group.",
                )

            wbs_clean = (alloc_in.wbs_code or "").strip()
            if not wbs_clean:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Allocation #{idx} must have a WBS code.",
                )

            amt = Decimal(str(alloc_in.amount_gst)).quantize(Decimal("0.01"))
            if amt <= Decimal("0.00"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    f"Allocation #{idx} ({wbs_clean}) amount must be greater than $0.00.",
                )

            lg, lab, cat = _validate_classification_ids(
                db, alloc_in.lab_group_id, alloc_in.lab_id, alloc_in.category_id
            )
            alloc_sum += amt

            prev_entry = (
                existing_allocs[idx - 1] if idx - 1 < len(existing_allocs) else {}
            )
            portion_key = prev_entry.get(
                "line_identity_key", f"{parent_identity_key}::alloc_{idx}"
            )
            validated_allocs.append(
                {
                    "allocation_index": idx,
                    "row_number": prev_entry.get("row_number", line.source_line_no),
                    "wbs": wbs_clean,
                    "mca": prev_entry.get("mca") or "Amount",
                    "raw_allocation": str(amt),
                    "quantity": prev_entry.get("quantity"),
                    "amount_gst": str(amt),
                    "amount_missing": False,
                    "suggested_lab_group_id": lg.lab_group_id,
                    "suggested_lab_id": lab.lab_id,
                    "suggested_category_id": cat.category_id,
                    "line_identity_key": portion_key,
                    "confirmed": True,
                }
            )

        if abs(alloc_sum - line_amount) > Decimal("0.01"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                (
                    f"WBS allocation portions sum to ${alloc_sum:,.2f}, which does not "
                    f"reconcile with the original purchase line amount of ${line_amount:,.2f}."
                ),
            )

        raw_json["wbs_allocations"] = validated_allocs
        raw_json["allocations_reconciled"] = True
        raw_json["allocated_total_gst"] = str(alloc_sum)
        line.raw_line_json = raw_json

        primary_group_id = validated_allocs[0]["suggested_lab_group_id"]
        primary_lab_id = validated_allocs[0]["suggested_lab_id"]
        primary_cat_id = validated_allocs[0]["suggested_category_id"]

        line.suggested_lab_group_id = primary_group_id
        line.suggested_lab_id = primary_lab_id
        line.suggested_category_id = primary_cat_id
        line.review_status = "resolved"
        line.classification_status = "confident"

        new_values: dict[str, Any] = {
            "suggested_lab_group_id": primary_group_id,
            "suggested_lab_id": primary_lab_id,
            "suggested_category_id": primary_cat_id,
            "review_status": "resolved",
            "wbs_allocations": validated_allocs,
        }
    else:
        # ─── Path B: Top-Level Classification Correction ──────────────────
        if body.lab_group_id is None or body.lab_id is None or body.category_id is None:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "lab_group_id, lab_id, and category_id are required.",
            )

        if role_name == "teamlead" and body.lab_group_id != current_user.lab_group_id:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "Team Leads can only assign lines within their own assigned Lab Group.",
            )

        lg, lab, cat = _validate_classification_ids(
            db, body.lab_group_id, body.lab_id, body.category_id
        )

        # If this line has multi-WBS allocations, ensure their amounts reconcile before allowing resolution
        if len(existing_allocs) > 1:
            any_missing = any(
                bool(a.get("amount_missing")) or a.get("amount_gst") is None
                for a in existing_allocs
            )
            if any_missing:
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    (
                        "Cannot resolve multi-WBS line with missing allocation amounts. "
                        f"Provide exact allocation amounts summing to ${line_amount:,.2f}."
                    ),
                )
            alloc_sum = sum(
                (Decimal(str(a["amount_gst"])) for a in existing_allocs),
                Decimal("0.00"),
            ).quantize(Decimal("0.01"))
            if abs(alloc_sum - line_amount) > Decimal("0.01"):
                raise HTTPException(
                    status.HTTP_400_BAD_REQUEST,
                    (
                        f"WBS allocation portions sum to ${alloc_sum:,.2f}, which does not "
                        f"reconcile with the original purchase line amount of ${line_amount:,.2f}."
                    ),
                )
            general_group = (
                db.query(LabGroup).filter(LabGroup.lab_group_name == "General").first()
            )
            general_group_id = general_group.lab_group_id if general_group else None
            updated_allocs: list[dict[str, Any]] = []
            for a in existing_allocs:
                a_copy = dict(a)
                if (
                    a_copy.get("suggested_lab_group_id") in (None, general_group_id)
                    or a_copy.get("suggested_lab_group_id") == lg.lab_group_id
                ):
                    a_copy["suggested_lab_group_id"] = lg.lab_group_id
                    a_copy["suggested_lab_id"] = lab.lab_id
                a_copy["suggested_category_id"] = cat.category_id
                a_copy["confirmed"] = True
                updated_allocs.append(a_copy)
            raw_json["wbs_allocations"] = updated_allocs
            raw_json["allocations_reconciled"] = True
            raw_json["allocated_total_gst"] = str(alloc_sum)
            line.raw_line_json = raw_json

        line.suggested_lab_group_id = lg.lab_group_id
        line.suggested_lab_id = lab.lab_id
        line.suggested_category_id = cat.category_id
        line.review_status = "resolved"
        line.classification_status = "confident"

        new_values = {
            "suggested_lab_group_id": lg.lab_group_id,
            "suggested_lab_id": lab.lab_id,
            "suggested_category_id": cat.category_id,
            "review_status": "resolved",
        }
        if len(existing_allocs) > 1:
            new_values["wbs_allocations"] = raw_json["wbs_allocations"]

    item.queue_status = "resolved"
    item.resolved_at = func.now()

    db.add(
        ReviewAction(
            review_queue_id=item.review_queue_id,
            reviewed_by=current_user.user_id,
            final_lab_group_id=line.suggested_lab_group_id,
            final_lab_id=line.suggested_lab_id,
            final_category_id=line.suggested_category_id,
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

    if role_name == "teamlead":
        if current_user.lab_group_id is None:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "Team Lead is not assigned to a lab group."
            )
        all_batch_lines = (
            db.query(StagingPRLine)
            .join(
                StagingPRHeader,
                StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
            )
            .filter(StagingPRHeader.batch_id == batch_id)
            .all()
        )
        if not any(
            _line_in_teamlead_scope(s_line, current_user.lab_group_id)
            for s_line in all_batch_lines
        ):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                "This batch has no lines in your assigned lab group.",
            )

    # ─── Pre-Commit Multi-WBS Reconciliation Validation ───────────────────
    pre_lab_ids: set[int] = set()
    pre_group_ids: set[int] = set()

    for header in headers:
        staging_lines = (
            db.query(StagingPRLine)
            .filter(StagingPRLine.staging_header_id == header.staging_header_id)
            .order_by(StagingPRLine.source_line_no)
            .all()
        )
        pr_has_multi_wbs = False
        pr_lines_sum = Decimal("0.00")
        staged_base_keys: set[str] = set()

        for s_line in staging_lines:
            if s_line.suggested_lab_id:
                pre_lab_ids.add(s_line.suggested_lab_id)
            if s_line.suggested_lab_group_id:
                pre_group_ids.add(s_line.suggested_lab_group_id)

            parent_key = _raw_line_value(s_line, "line_identity_key")
            if parent_key:
                staged_base_keys.add(_base_identity_key(parent_key))

            line_amt = Decimal(str(s_line.amount_gst or 0)).quantize(Decimal("0.01"))
            pr_lines_sum += line_amt

            allocs = _raw_wbs_allocations(s_line)
            if len(allocs) > 1:
                pr_has_multi_wbs = True
                for alloc in allocs:
                    if alloc.get("suggested_lab_id"):
                        pre_lab_ids.add(int(alloc["suggested_lab_id"]))
                    if alloc.get("suggested_lab_group_id"):
                        pre_group_ids.add(int(alloc["suggested_lab_group_id"]))

                any_missing = any(
                    bool(a.get("amount_missing")) or a.get("amount_gst") is None
                    for a in allocs
                )
                if any_missing:
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        (
                            f"Cannot commit batch {batch_id}: PR {header.source_pr_number} "
                            f"line {s_line.source_line_no} has missing WBS allocation amounts."
                        ),
                    )

                alloc_sum = sum(
                    (Decimal(str(a["amount_gst"])) for a in allocs),
                    Decimal("0.00"),
                ).quantize(Decimal("0.01"))
                if abs(alloc_sum - line_amt) > Decimal("0.01"):
                    raise HTTPException(
                        status.HTTP_409_CONFLICT,
                        (
                            f"Cannot commit batch {batch_id}: PR {header.source_pr_number} "
                            f"line {s_line.source_line_no} WBS allocations (${alloc_sum:,.2f}) "
                            f"do not reconcile with purchase line amount (${line_amt:,.2f})."
                        ),
                    )

        if pr_has_multi_wbs and header.grand_total_sgd is not None:
            # Include any unchanged already-committed lines on this PR that were skipped as duplicates on re-upload
            existing_pr_check = (
                db.query(PurchaseRequest)
                .filter(PurchaseRequest.source_pr_number == header.source_pr_number)
                .first()
            )
            if existing_pr_check is not None:
                existing_map = _existing_committed_lines_by_identity(
                    db, existing_pr_check
                )
                for ex_key, ex_line in existing_map.items():
                    if _base_identity_key(ex_key) not in staged_base_keys:
                        pr_lines_sum += Decimal(str(ex_line.amount_gst or 0)).quantize(
                            Decimal("0.01")
                        )

            header_grand = Decimal(str(header.grand_total_sgd)).quantize(
                Decimal("0.01")
            )
            if header_grand > Decimal("0.00") and abs(
                pr_lines_sum - header_grand
            ) > Decimal("0.01"):
                raise HTTPException(
                    status.HTTP_409_CONFLICT,
                    (
                        f"Cannot commit batch {batch_id}: PR {header.source_pr_number} "
                        f"committed line totals (${pr_lines_sum:,.2f}) do not reconcile "
                        f"with PR grand total (${header_grand:,.2f})."
                    ),
                )

    _sync_pre_commit_threshold_flags(db, pre_lab_ids, pre_group_ids)

    pr_ids: list[int] = []
    prs_created_count = 0
    prs_updated_count = 0
    lines_created = 0
    lines_updated = 0
    status_regressions_skipped = 0

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

        existing_lines_by_identity = _existing_committed_lines_by_identity(db, pr)
        status_updates: list[dict] = []
        allocation_updates: list[dict] = []
        amount_updates: list[dict] = []
        regressions_skipped: list[dict] = []
        committed_line_units = 0

        for line in lines:
            allocs = _raw_wbs_allocations(line)
            parent_identity_key = _raw_line_value(line, "line_identity_key")
            incoming_status = _raw_line_value(line, "pr_status")

            # ─── Commit Multi-WBS Exact Allocation Portions ───────────────
            if len(allocs) > 1:
                prefix = f"{parent_identity_key}::alloc_"
                existing_portion_map: dict[str, PurchaseRequestLine] = {
                    k: v
                    for k, v in existing_lines_by_identity.items()
                    if k.startswith(prefix)
                }
                if (
                    not existing_portion_map
                    and parent_identity_key in existing_lines_by_identity
                ):
                    existing_portion_map[f"{parent_identity_key}::alloc_1"] = (
                        existing_lines_by_identity[parent_identity_key]
                    )

                # Check status regression against any existing committed portion
                regressed_existing = next(
                    (
                        ex_line
                        for ex_line in existing_portion_map.values()
                        if is_status_regression(ex_line.pr_status, incoming_status)
                    ),
                    None,
                )
                if regressed_existing is not None:
                    line.duplicate_status = "status_regression"
                    regressions_skipped.append(
                        {
                            "line_identity_key": parent_identity_key,
                            "line_no": line.source_line_no,
                            "staging_line_id": line.staging_line_id,
                            "accepted_status": regressed_existing.pr_status,
                            "attempted_status": incoming_status,
                        }
                    )
                    if line is lines[0]:
                        pr.pr_status = regressed_existing.pr_status
                    continue

                used_keys: set[str] = set()
                base_desc = (line.item_details or "Purchase Item").strip()

                for idx, alloc in enumerate(allocs, start=1):
                    portion_key = str(
                        alloc.get("line_identity_key")
                        or f"{parent_identity_key}::alloc_{idx}"
                    )
                    used_keys.add(portion_key)

                    alloc_wbs = str(alloc.get("wbs") or "").strip()
                    alloc_amt = Decimal(str(alloc["amount_gst"])).quantize(
                        Decimal("0.01")
                    )
                    alloc_lab_id = (
                        alloc.get("suggested_lab_id") or line.suggested_lab_id
                    )
                    alloc_group_id = (
                        alloc.get("suggested_lab_group_id")
                        or line.suggested_lab_group_id
                    )
                    alloc_cat_id = (
                        alloc.get("suggested_category_id") or line.suggested_category_id
                    )
                    alloc_qty = (
                        Decimal(str(alloc["quantity"]))
                        if alloc.get("quantity") is not None
                        else line.qty
                    )

                    if alloc_lab_id:
                        affected_lab_ids.add(int(alloc_lab_id))
                    if alloc_group_id:
                        affected_lab_group_ids.add(int(alloc_group_id))

                    portion_desc = (
                        f"{base_desc} [WBS: {alloc_wbs}]"
                        if alloc_wbs and f"[WBS: {alloc_wbs}]" not in base_desc
                        else base_desc
                    )

                    existing_portion = existing_portion_map.get(portion_key)
                    if existing_portion is not None:
                        old_snapshot = {
                            "wbs": alloc_wbs,
                            "amount_gst": str(existing_portion.amount_gst),
                            "lab_id": existing_portion.lab_id,
                            "category_id": existing_portion.category_id,
                            "pr_status": existing_portion.pr_status,
                        }
                        existing_portion.line_no = line.source_line_no
                        existing_portion.item_description = portion_desc
                        existing_portion.qty = alloc_qty
                        existing_portion.unit_rate = line.unit_rate
                        existing_portion.amount_gst = alloc_amt
                        existing_portion.lab_id = alloc_lab_id
                        existing_portion.category_id = alloc_cat_id
                        existing_portion.source_staging_line_id = line.staging_line_id
                        existing_portion.pr_status = incoming_status or None
                        lines_updated += 1
                        new_snapshot = {
                            "wbs": alloc_wbs,
                            "amount_gst": str(alloc_amt),
                            "lab_id": alloc_lab_id,
                            "category_id": alloc_cat_id,
                            "pr_status": incoming_status or None,
                        }
                        if old_snapshot != new_snapshot:
                            allocation_updates.append(
                                {
                                    "line_identity_key": portion_key,
                                    "old": old_snapshot,
                                    "new": new_snapshot,
                                }
                            )
                    else:
                        db.add(
                            PurchaseRequestLine(
                                pr_id=pr.pr_id,
                                line_no=line.source_line_no,
                                item_description=portion_desc,
                                qty=alloc_qty,
                                unit_rate=line.unit_rate,
                                amount_gst=alloc_amt,
                                currency_code="SGD",
                                lab_id=alloc_lab_id,
                                category_id=alloc_cat_id,
                                source_staging_line_id=line.staging_line_id,
                                pr_status=incoming_status or None,
                            )
                        )
                        lines_created += 1

                # Remove any obsolete extra allocation rows if portion count shrunk on re-upload
                for old_key, old_portion_line in existing_portion_map.items():
                    if old_key not in used_keys:
                        db.delete(old_portion_line)

                committed_line_units += 1
                continue

            # ─── Standard Single-Line Commit ──────────────────────────────
            line_identity_key = parent_identity_key
            existing_line = existing_lines_by_identity.get(line_identity_key)

            # W17: approval is final; an upload cannot move an Approved line
            # to any non-Approved status.
            if existing_line and is_status_regression(
                existing_line.pr_status, incoming_status
            ):
                line.duplicate_status = "status_regression"
                regressions_skipped.append(
                    {
                        "line_identity_key": line_identity_key,
                        "line_no": line.source_line_no,
                        "staging_line_id": line.staging_line_id,
                        "accepted_status": existing_line.pr_status,
                        "attempted_status": incoming_status,
                    }
                )
                if line is lines[0]:
                    # Header status follows the first line; keep it accepted.
                    pr.pr_status = existing_line.pr_status
                continue

            if line.suggested_lab_id:
                affected_lab_ids.add(line.suggested_lab_id)
            if line.suggested_lab_group_id:
                affected_lab_group_ids.add(line.suggested_lab_group_id)

            if existing_line:
                old_staging_line = _staging_line_for_committed_line(db, existing_line)
                old_status = _source_status_snapshot(old_staging_line)
                new_status = _source_status_snapshot(line)

                existing_line.source_staging_line_id = line.staging_line_id
                existing_line.pr_status = incoming_status or None
                # Procurement can revise a PR after it is saved, so the latest
                # file's money replaces the old figures. Lab and category stay
                # as reviewed.
                if (
                    line.amount_gst is not None
                    and line.amount_gst != existing_line.amount_gst
                ):
                    amount_updates.append(
                        {
                            "line_no": line.source_line_no,
                            "old_amount": str(existing_line.amount_gst),
                            "new_amount": str(line.amount_gst),
                        }
                    )
                    existing_line.amount_gst = line.amount_gst
                if line.qty is not None:
                    existing_line.qty = line.qty
                if line.unit_rate is not None:
                    existing_line.unit_rate = line.unit_rate
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
                committed_line_units += 1
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
                    pr_status=incoming_status or None,
                )
            )
            lines_created += 1
            committed_line_units += 1

        db.flush()
        # A blocked line keeps its old amount, so the file's total no longer
        # matches. Rebuild the PR total from the saved lines instead.
        if regressions_skipped:
            pr.grand_total_sgd = (
                db.query(func.sum(PurchaseRequestLine.amount_gst))
                .filter(PurchaseRequestLine.pr_id == pr.pr_id)
                .scalar()
            )
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
        if allocation_updates:
            new_data["allocation_updates"] = [u["new"] for u in allocation_updates]
            if old_data is None:
                old_data = {}
            old_data["allocation_updates"] = [u["old"] for u in allocation_updates]
        if amount_updates:
            new_data["amount_updates"] = amount_updates
        if regressions_skipped:
            new_data["status_regressions_skipped"] = regressions_skipped
            status_regressions_skipped += len(regressions_skipped)

        # Skipped lines trigger no threshold or vector refresh work.
        if committed_line_units > 0:
            pr_ids.append(pr.pr_id)
            if pr_lab_group_id:
                affected_lab_group_ids.add(pr_lab_group_id)

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
                "status_regressions_skipped": status_regressions_skipped,
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
        status_regressions_skipped=status_regressions_skipped,
    )


# ─── Helpers ─────────────────────────────────────────────────────────────
def _base_identity_key(raw_key: str) -> str:
    for sep in ("::alloc_", "::lab_"):
        if sep in raw_key:
            return raw_key.split(sep, 1)[0]
    return raw_key


def _validate_classification_ids(
    db: Session, lab_group_id: int, lab_id: int, category_id: int
) -> tuple[LabGroup, Lab, SpendingCategory]:
    lab_group = db.query(LabGroup).filter(LabGroup.lab_group_id == lab_group_id).first()
    if not lab_group:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown lab_group_id={lab_group_id}."
        )
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, f"Unknown lab_id={lab_id}.")
    if lab.lab_group_id != lab_group_id:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            f"Lab '{lab.lab_name}' does not belong to lab_group '{lab_group.lab_group_name}'.",
        )
    category = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == category_id)
        .first()
    )
    if not category:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, f"Unknown category_id={category_id}."
        )
    return lab_group, lab, category


def _raw_wbs_allocations(line: StagingPRLine | None) -> list[dict[str, Any]]:
    if line is None or not isinstance(line.raw_line_json, dict):
        return []
    allocs = line.raw_line_json.get("wbs_allocations")
    if not isinstance(allocs, list):
        return []
    return [a for a in allocs if isinstance(a, dict)]


def _line_in_teamlead_scope(line: StagingPRLine, user_lab_group_id: int | None) -> bool:
    """
    A Team Lead may review or edit a line only when it falls entirely within
    that Team Lead's assigned Lab Group:
      - For a multi-WBS line, EVERY allocation portion must belong to `user_lab_group_id`.
        Lines spanning multiple Lab Groups (or containing any portion outside the Team
        Lead's Lab Group) require Admin review.
      - For a single-WBS line, `line.suggested_lab_group_id` must match `user_lab_group_id`.
    """
    if user_lab_group_id is None:
        return False
    allocs = _raw_wbs_allocations(line)
    if len(allocs) > 1:
        return all(
            (alloc.get("suggested_lab_group_id") or line.suggested_lab_group_id)
            == user_lab_group_id
            for alloc in allocs
        )
    return line.suggested_lab_group_id == user_lab_group_id


def _build_wbs_allocation_items(
    line: StagingPRLine,
    lg_name_by_id: dict[int, str],
    lab_name_by_id: dict[int, str],
    cat_name_by_id: dict[int, str],
) -> tuple[list[WBSAllocationItem], bool, str | None]:
    raw_allocs = _raw_wbs_allocations(line)
    if len(raw_allocs) <= 1:
        return [], True, None

    items: list[WBSAllocationItem] = []
    any_missing = False
    alloc_sum = Decimal("0.00")

    for idx, alloc in enumerate(raw_allocs, start=1):
        lg_id = alloc.get("suggested_lab_group_id") or line.suggested_lab_group_id
        l_id = alloc.get("suggested_lab_id") or line.suggested_lab_id
        c_id = alloc.get("suggested_category_id") or line.suggested_category_id

        lg_name = lg_name_by_id.get(lg_id, "General") if lg_id else "General"
        l_name = lab_name_by_id.get(l_id, "General") if l_id else "General"
        c_name = cat_name_by_id.get(c_id, "General") if c_id else "General"

        raw_amt = alloc.get("amount_gst")
        amt_missing = bool(alloc.get("amount_missing")) or raw_amt is None
        amt_str: str | None = None
        if not amt_missing:
            try:
                dec = Decimal(str(raw_amt)).quantize(Decimal("0.01"))
                alloc_sum += dec
                amt_str = str(dec)
            except Exception:
                amt_missing = True

        if amt_missing:
            any_missing = True

        items.append(
            WBSAllocationItem(
                allocation_index=int(alloc.get("allocation_index") or idx),
                row_number=alloc.get("row_number"),
                wbs_code=str(alloc.get("wbs") or ""),
                mca=alloc.get("mca"),
                amount_gst=amt_str,
                amount_missing=amt_missing,
                suggested_lab_group_id=lg_id,
                suggested_lab_id=l_id,
                suggested_category_id=c_id,
                current_lab_group=lg_name,
                current_lab=l_name,
                current_category=c_name,
                is_lab_group_general=lg_name.lower() == "general",
                is_lab_general=l_name.lower() == "general",
                is_category_general=c_name.lower() == "general",
            )
        )

    line_amt = Decimal(str(line.amount_gst or 0)).quantize(Decimal("0.01"))
    reconciles = not any_missing and abs(alloc_sum - line_amt) <= Decimal("0.01")
    return items, reconciles, str(alloc_sum)


def _sync_pre_commit_threshold_flags(
    db: Session, lab_ids: set[int], group_ids: set[int]
) -> None:
    """
    Syncs notification flags with actual pre-commit utilization before new PR lines
    are committed, so stale `notified_50=True` flags (e.g. after deleting test PRs)
    are cleared if pre-commit utilization was below the threshold.
    """
    try:
        today = date.today()
        current_period = (
            db.query(BudgetPeriod)
            .filter(BudgetPeriod.start_date <= today, BudgetPeriod.end_date >= today)
            .first()
        )
        if not isinstance(current_period, BudgetPeriod):
            return

        active_status_filter = or_(
            PurchaseRequestLine.pr_status.is_(None),
            and_(
                PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
            ),
        )

        for lid in lab_ids:
            lab = db.query(Lab).filter(Lab.lab_id == lid).first()
            if not isinstance(lab, Lab):
                continue
            if lab.lab_group_id:
                group_ids.add(lab.lab_group_id)

            total_budget = float(
                db.query(func.sum(Budget.budget_amount))
                .filter(
                    Budget.lab_id == lid,
                    Budget.period_id == current_period.period_id,
                )
                .scalar()
                or 0
            )
            if total_budget <= 0:
                lab.notified_50 = False
                lab.notified_80 = False
                lab.notified_95 = False
                lab.notified_100 = False
                continue

            pre_spent = float(
                db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(
                    PurchaseRequest,
                    PurchaseRequest.pr_id == PurchaseRequestLine.pr_id,
                )
                .filter(
                    PurchaseRequestLine.lab_id == lid,
                    PurchaseRequest.request_date >= current_period.start_date,
                    PurchaseRequest.request_date <= current_period.end_date,
                    active_status_filter,
                )
                .scalar()
                or 0
            )
            pre_util = (pre_spent / total_budget) * 100
            if pre_util < 100:
                lab.notified_100 = False
            if pre_util < 95:
                lab.notified_95 = False
            if pre_util < 80:
                lab.notified_80 = False
            if pre_util < 50:
                lab.notified_50 = False

        for gid in group_ids:
            group = db.query(LabGroup).filter(LabGroup.lab_group_id == gid).first()
            if not isinstance(group, LabGroup):
                continue

            env_budget = float(
                db.query(func.sum(Budget.budget_amount))
                .filter(
                    Budget.lab_group_id == gid,
                    Budget.lab_id.is_(None),
                    Budget.period_id == current_period.period_id,
                )
                .scalar()
                or 0
            )
            if env_budget <= 0:
                group.notified_50 = False
                group.notified_80 = False
                group.notified_95 = False
                group.notified_100 = False
                continue

            pre_group_spent = float(
                db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(
                    PurchaseRequest,
                    PurchaseRequest.pr_id == PurchaseRequestLine.pr_id,
                )
                .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
                .filter(
                    Lab.lab_group_id == gid,
                    PurchaseRequest.request_date >= current_period.start_date,
                    PurchaseRequest.request_date <= current_period.end_date,
                    active_status_filter,
                )
                .scalar()
                or 0
            )
            pre_group_util = (pre_group_spent / env_budget) * 100
            if pre_group_util < 100:
                group.notified_100 = False
            if pre_group_util < 95:
                group.notified_95 = False
            if pre_group_util < 80:
                group.notified_80 = False
            if pre_group_util < 50:
                group.notified_50 = False

        db.flush()
    except Exception:
        pass


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
    all_lines = sorted(pr.lines, key=lambda item: item.pr_line_id or 0)
    by_staging_id: dict[int, list[PurchaseRequestLine]] = {}
    for line in all_lines:
        if line.source_staging_line_id is not None:
            by_staging_id.setdefault(line.source_staging_line_id, []).append(line)

    for staging_id, grouped_lines in by_staging_id.items():
        staging_line = (
            db.query(StagingPRLine)
            .filter(StagingPRLine.staging_line_id == staging_id)
            .first()
        )
        if staging_line is None or not isinstance(staging_line.raw_line_json, dict):
            continue
        allocs = _raw_wbs_allocations(staging_line)
        parent_key = _raw_line_value(staging_line, "line_identity_key")
        if len(allocs) > 1 and len(grouped_lines) > 1:
            for idx, final_line in enumerate(grouped_lines, start=1):
                alloc_entry = allocs[idx - 1] if idx - 1 < len(allocs) else {}
                portion_key = str(
                    alloc_entry.get("line_identity_key") or f"{parent_key}::alloc_{idx}"
                )
                lines_by_identity[portion_key] = final_line
        else:
            if parent_key:
                lines_by_identity[parent_key] = grouped_lines[0]
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

    open_rows = (
        db.query(ReviewQueueItem, StagingPRLine)
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
        .all()
    )
    if role_name == "teamlead" and user_lab_group_id is not None:
        open_rows = [
            (q_item, s_line)
            for q_item, s_line in open_rows
            if _line_in_teamlead_scope(s_line, user_lab_group_id)
        ]
    open_count = len(open_rows)

    return BatchSummary(
        batch_id=batch.batch_id,
        filename=batch.filename,
        upload_status=batch.upload_status,
        uploaded_at=batch.uploaded_at,
        uploader_name=batch.uploader.full_name if batch.uploader else "Unknown",
        total_lines=total_lines,
        open_queue_count=open_count,
    )
