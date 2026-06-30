"""
PR Records API endpoints.

Read-only view of committed purchase requests (the official historical
record). Foundation for W9-02's 'Historical retrieval test' requirement
and a stepping stone for W11-03 reporting work.
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.config import Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.models.auth import User

router = APIRouter(prefix="/api/records", tags=["Records"])

# Lab IC hidden from this page in the sidebar; backend matches by returning 403.
# To re-enable Lab IC access later: add "labic" to this set.
ALLOWED_RECORDS_ROLES = {"admin", "teamlead"}


# ─── Response shapes ─────────────────────────────────────────────────────
class CommittedPRLine(BaseModel):
    pr_line_id: int
    line_no: int | None
    item_description: str
    qty: str | None
    unit_rate: str | None
    amount_gst: str
    currency_code: str
    lab_name: str
    category_name: str
    source_staging_line_id: int | None
    # Per-line source-system status (e.g. "Approved (SVP)", "Pending Approval",
    # "Rejected"). A PR can have lines in different states.
    pr_status: str | None


class CommittedPR(BaseModel):
    pr_id: int
    source_pr_number: str
    requestor_name: str
    purpose: str
    wbs_code: str
    grand_total_sgd: str
    lab_group_name: str
    latest_batch_id: int | None
    updated_at: datetime
    # System lifecycle status — always "committed" for rows on this endpoint.
    status: str
    # Source-system PR Status from the latest xlsx (e.g. "Approved (SVP)",
    # "Pending Approval", "Rejected"). Null if the column wasn't populated.
    pr_status: str | None
    lines: list[CommittedPRLine]


# ─── Endpoint ────────────────────────────────────────────────────────────
@router.get("/prs", response_model=list[CommittedPR])
def list_committed_prs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommittedPR]:
    """
    Return all committed purchase requests (with their lines).

    Role scoping:
      - Admin     → every committed PR.
      - Team Lead → only PRs whose lab_group_id matches their lab_group_id.
      - Lab IC    → 403 (page hidden in sidebar; backend mirror).

    Sorted most-recently-updated first so the freshest data sits at the top.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_RECORDS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view PR Records.",
        )

    query = db.query(PurchaseRequest)
    if role_name == "teamlead":
        if not current_user.lab_group_id:
            return []
        query = query.filter(PurchaseRequest.lab_group_id == current_user.lab_group_id)

    prs = query.order_by(PurchaseRequest.updated_at.desc()).all()
    if not prs:
        return []

    # Pre-fetch all lab/category/group names so we don't N+1.
    lab_names = {lab.lab_id: lab.lab_name for lab in db.query(Lab).all()}
    cat_names = {
        c.category_id: c.category_name for c in db.query(SpendingCategory).all()
    }
    group_names = {g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()}

    pr_ids = [pr.pr_id for pr in prs]
    all_lines = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.pr_id.in_(pr_ids))
        .order_by(PurchaseRequestLine.pr_id, PurchaseRequestLine.line_no)
        .all()
    )
    lines_by_pr: dict[int, list[PurchaseRequestLine]] = {}
    for line in all_lines:
        lines_by_pr.setdefault(line.pr_id, []).append(line)

    return [
        CommittedPR(
            pr_id=pr.pr_id,
            source_pr_number=pr.source_pr_number,
            requestor_name=pr.requestor_name or "",
            purpose=pr.purpose or "",
            wbs_code=pr.wbs_code or "",
            grand_total_sgd=str(pr.grand_total_sgd)
            if pr.grand_total_sgd is not None
            else "0",
            lab_group_name=group_names.get(pr.lab_group_id, "General"),
            latest_batch_id=pr.latest_batch_id,
            updated_at=pr.updated_at,
            status="committed",
            pr_status=pr.pr_status,
            lines=[
                CommittedPRLine(
                    pr_line_id=line.pr_line_id,
                    line_no=line.line_no,
                    item_description=line.item_description or "",
                    qty=str(line.qty) if line.qty is not None else None,
                    unit_rate=str(line.unit_rate)
                    if line.unit_rate is not None
                    else None,
                    amount_gst=str(line.amount_gst)
                    if line.amount_gst is not None
                    else "0",
                    currency_code=line.currency_code or "SGD",
                    lab_name=lab_names.get(line.lab_id, "General"),
                    category_name=cat_names.get(line.category_id, "General"),
                    source_staging_line_id=line.source_staging_line_id,
                    pr_status=line.pr_status,
                )
                for line in lines_by_pr.get(pr.pr_id, [])
            ],
        )
        for pr in prs
    ]


# ─── Helpers ─────────────────────────────────────────────────────────────
def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()
