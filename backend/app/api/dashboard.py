"""
Dashboard aggregation API (W11-01).

Spending / utilization numbers the dashboard cards consume.
Lives separate from /api/records so the dashboard never has to
download line-by-line data just to render one number.
"""
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.config import Lab
from app.models.staging import PurchaseRequestLine

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

ALLOWED_DASHBOARD_ROLES = {"admin", "teamlead"}


# ─── Response shapes ─────────────────────────────────────────────────────
class SpendingSummary(BaseModel):
    """Approved spend (actual) + Pending spend (committed-but-not-approved),
    each with a per-lab-group breakdown so the dashboard dropdown can filter
    without a second round-trip."""

    total_actual_spend_sgd: str            # sum of lines where status starts with "Approved"
    by_lab_group: dict[str, str]           # ^ broken down per lab_group_id
    total_pending_sgd: str                 # sum of lines where status starts with "Pending"
    pending_by_lab_group: dict[str, str]   # ^ broken down per lab_group_id


# ─── Endpoint ────────────────────────────────────────────────────────────
@router.get("/spending", response_model=SpendingSummary)
def get_spending_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> SpendingSummary:
    """
    Two parallel aggregates over purchase_request_lines:
      - Approved (pr_status ILIKE 'approved%') → actual spend
      - Pending  (pr_status ILIKE 'pending%')  → committed but not yet approved

    Both grouped by the line's lab's lab_group_id so the dashboard dropdown
    can filter client-side.

    Role scoping:
      - Admin     → every lab group counted.
      - Team Lead → only their lab_group's labs.
      - Lab IC    → 403 (dashboard isn't theirs).

    Lines whose lab_id is NULL or whose lab has no lab_group_id end up
    under the "0" bucket so they're still reflected in the totals.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_DASHBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view dashboard spending.",
        )

    if role_name == "teamlead" and not current_user.lab_group_id:
        return SpendingSummary(
            total_actual_spend_sgd="0",
            by_lab_group={},
            total_pending_sgd="0",
            pending_by_lab_group={},
        )

    approved_by_group, approved_total = _aggregate_by_status(
        db, "approved%", role_name, current_user.lab_group_id
    )
    pending_by_group, pending_total = _aggregate_by_status(
        db, "pending%", role_name, current_user.lab_group_id
    )

    return SpendingSummary(
        total_actual_spend_sgd=str(approved_total),
        by_lab_group=approved_by_group,
        total_pending_sgd=str(pending_total),
        pending_by_lab_group=pending_by_group,
    )


def _aggregate_by_status(
    db: Session, status_pattern: str, role_name: str, user_lab_group_id: int | None
) -> tuple[dict[str, str], Decimal]:
    query = (
        db.query(
            Lab.lab_group_id,
            func.coalesce(func.sum(PurchaseRequestLine.amount_gst), 0),
        )
        .outerjoin(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .filter(PurchaseRequestLine.pr_status.ilike(status_pattern))
        .group_by(Lab.lab_group_id)
    )
    if role_name == "teamlead":
        query = query.filter(Lab.lab_group_id == user_lab_group_id)

    by_group: dict[str, str] = {}
    total = Decimal("0")
    for lab_group_id, amount in query.all():
        key = str(lab_group_id) if lab_group_id is not None else "0"
        amount_decimal = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        by_group[key] = str(amount_decimal)
        total += amount_decimal
    return by_group, total


def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()
