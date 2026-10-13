"""
Dashboard aggregation API (W11-01).

Spending / utilization numbers the dashboard cards consume.
Lives separate from /api/records so the dashboard never has to
download line-by-line data just to render one number.
"""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.api.config import get_lab_groups
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.services.dashboard_report_service import (
    DashboardKpis,
    DashboardMeta,
    build_dashboard_workbook,
)
from app.utils.date_range import date_range_bounds

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

ALLOWED_DASHBOARD_ROLES = {"admin", "teamlead", "labic"}

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

DASHBOARD_ROLE_LABELS = {
    "admin": "Admin",
    "teamlead": "Team Lead",
    "labic": "Lab IC",
}

# Mirror of the dashboard FilterBar "Date Range" option labels.
DASHBOARD_RANGE_LABELS = {
    "all": "Whole year",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "90d": "Last 90 days",
    "ytd": "Year to date",
}


# ─── Response shapes ─────────────────────────────────────────────────────
class SpendingSummary(BaseModel):
    """Approved spend (actual) + Pending spend (committed-but-not-approved),
    each with a per-lab-group breakdown so the dashboard dropdown can filter
    without a second round-trip."""

    total_actual_spend_sgd: str  # sum of lines where status starts with "Approved"
    by_lab_group: dict[str, str]  # ^ broken down per lab_group_id
    total_pending_sgd: str  # sum of lines where status starts with "Pending"
    pending_by_lab_group: dict[str, str]  # ^ broken down per lab_group_id


# ─── Endpoint ────────────────────────────────────────────────────────────
@router.get("/spending", response_model=SpendingSummary)
def get_spending_summary(
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
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

    # Team Lead with no group / Lab IC with no lab → nothing in scope.
    user_lab_ids = (
        [a.lab_id for a in current_user.lab_assignments] if role_name == "labic" else []
    )
    if (role_name == "teamlead" and not current_user.lab_group_id) or (
        role_name == "labic" and not user_lab_ids
    ):
        return SpendingSummary(
            total_actual_spend_sgd="0",
            by_lab_group={},
            total_pending_sgd="0",
            pending_by_lab_group={},
        )

    start, end = _resolve_bounds(date_range, start_date, end_date)
    approved_by_group, approved_total = _aggregate_by_status(
        db, "approved%", current_user, start, end
    )
    pending_by_group, pending_total = _aggregate_by_status(
        db, "pending%", current_user, start, end
    )

    return SpendingSummary(
        total_actual_spend_sgd=str(approved_total),
        by_lab_group=approved_by_group,
        total_pending_sgd=str(pending_total),
        pending_by_lab_group=pending_by_group,
    )


def _resolve_bounds(date_range, start_date, end_date):
    """Custom start/end wins; otherwise the preset (date_range_bounds handles
    'fy' with both ends and the relative windows with a lower bound)."""
    if start_date is not None or end_date is not None:
        return start_date, end_date
    return date_range_bounds(date_range)


def _apply_date_bounds(query, start, end):
    """
    Restrict a PurchaseRequestLine query to lines whose owning PR's request_date
    (the xlsx "PR Sub Date") falls within [start, end]. Budgets are never
    date-filtered — only spending. A NULL request_date fails the >= / <=
    comparison, so undated PRs drop out whenever any bound is active.
    """
    if start is None and end is None:
        return query
    query = query.join(
        PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id
    )
    if start is not None:
        query = query.filter(PurchaseRequest.request_date >= start)
    if end is not None:
        query = query.filter(PurchaseRequest.request_date <= end)
    return query


def _apply_role_scope(query, current_user):
    """
    Restrict query by caller's role:
      - Team Lead -> labs in their lab group.
      - Lab IC    -> all assigned labs (multi-lab support).
      - Admin     -> unrestricted.
    """
    role_name = _role_name(current_user)
    if role_name == "teamlead":
        return query.filter(Lab.lab_group_id == current_user.lab_group_id)
    if role_name == "labic":
        assigned_lab_ids = [a.lab_id for a in current_user.lab_assignments]
        return query.filter(PurchaseRequestLine.lab_id.in_(assigned_lab_ids))
    return query


def _aggregate_by_status(
    db: Session,
    status_pattern: str,
    current_user: User,
    start=None,
    end=None,
) -> tuple[dict[str, str], Decimal]:
    """
    Sum line amounts grouped by lab_group, filtered by pr_status pattern.

    Per spec rule #4: lines whose lab has no real Lab Group (orphan) OR whose
    lab_group is the "General" catch-all do NOT count toward any real Lab
    Group's reservation. They sit in unresolved review until a Team Lead
    re-classifies them.
    """
    query = (
        db.query(
            Lab.lab_group_id,
            func.coalesce(func.sum(PurchaseRequestLine.amount_gst), 0),
        )
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(PurchaseRequestLine.pr_status.ilike(status_pattern))
        .filter(LabGroup.lab_group_name != "General")
        .group_by(Lab.lab_group_id)
    )
    query = _apply_date_bounds(query, start, end)
    query = _apply_role_scope(query, current_user)

    by_group: dict[str, str] = {}
    total = Decimal("0")
    for lab_group_id, amount in query.all():
        # lab_group_id will never be NULL here (INNER joins ensure it),
        # but stringify defensively.
        key = str(lab_group_id) if lab_group_id is not None else "0"
        amount_decimal = amount if isinstance(amount, Decimal) else Decimal(str(amount))
        by_group[key] = str(amount_decimal)
        total += amount_decimal
    return by_group, total


def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()


def _current_period_id(db: Session) -> int | None:
    """period_id of the current fiscal year (Apr–Mar), or None if not set up.
    Budgets are per-FY, so the dashboard compares spend against the current
    year's budget rather than summing every year's budgets together."""
    today = date.today()
    year = today.year if today.month >= 4 else today.year - 1
    period = db.query(BudgetPeriod).filter(BudgetPeriod.year_no == year).first()
    return period.period_id if period else None


# ─── Breakdown (Lab Group → Lab → Category) ──────────────────────────────
class BreakdownCategory(BaseModel):
    # Nullable: a committed line whose category could not be resolved aggregates
    # into a single "Uncategorised" row rather than crashing the whole endpoint.
    category_id: int | None
    category_name: str
    budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float


class BreakdownLab(BaseModel):
    lab_id: int
    lab_name: str
    budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float
    categories: list[BreakdownCategory]


class BreakdownLabGroup(BaseModel):
    lab_group_id: int
    lab_group_name: str
    budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float
    labs: list[BreakdownLab]


class BreakdownResponse(BaseModel):
    lab_groups: list[BreakdownLabGroup]


@router.get("/breakdown", response_model=BreakdownResponse)
def get_breakdown(
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> BreakdownResponse:
    """
    Nested breakdown for the drilldown table: Lab Group → Lab → Category.

    Each level carries the same six metrics:
      budget, actual_spend, pending, available_balance, utilisation_pct,
      projected_utilisation_pct.

    Aggregation:
      - Category row = a single (lab_id, category_id) budget cell.
      - Lab row     = sum of its categories.
      - Lab Group   = sum of its labs.

    Inclusion rule: a (lab, category) appears if it has either a budget
    row OR any spending (so configured budgets show even at 0% util,
    and orphan spending isn't hidden).

    Per spec rule #4: the "General" Lab Group is excluded entirely — its
    lines sit in unresolved review.

    Role scoping:
      - Admin     → every (non-General) lab group.
      - Team Lead → only their assigned lab_group_id.
      - Lab IC    → 403.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_DASHBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view dashboard breakdown.",
        )
    user_lab_ids = (
        [a.lab_id for a in current_user.lab_assignments] if role_name == "labic" else []
    )
    if role_name == "labic" and not user_lab_ids:
        return BreakdownResponse(lab_groups=[])
    if role_name == "teamlead" and not current_user.lab_group_id:
        return BreakdownResponse(lab_groups=[])

    # ─── 1. Name lookups (one DB hit each) ────────────────────────────
    lab_group_names = {
        g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()
    }
    lab_names = {lab.lab_id: lab.lab_name for lab in db.query(Lab).all()}
    category_names = {
        c.category_id: c.category_name for c in db.query(SpendingCategory).all()
    }
    # Lab → lab_group lookup used to roll lines up to their owning group.
    lab_to_group: dict[int, int | None] = {
        lab.lab_id: lab.lab_group_id for lab in db.query(Lab).all()
    }

    # ─── 2. Spending per (lab, category), split by status ─────────────
    spending_query = (
        db.query(
            PurchaseRequestLine.lab_id,
            PurchaseRequestLine.category_id,
            func.coalesce(
                func.sum(
                    case(
                        (
                            PurchaseRequestLine.pr_status.ilike("approved%"),
                            PurchaseRequestLine.amount_gst,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
            func.coalesce(
                func.sum(
                    case(
                        (
                            PurchaseRequestLine.pr_status.ilike("pending%"),
                            PurchaseRequestLine.amount_gst,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .group_by(PurchaseRequestLine.lab_id, PurchaseRequestLine.category_id)
    )
    # Date filter applies to spending only; budgets stay full-FY (below).
    start, end = _resolve_bounds(date_range, start_date, end_date)
    spending_query = _apply_date_bounds(spending_query, start, end)
    spending_query = _apply_role_scope(spending_query, current_user)

    spending_by_lab_cat: dict[tuple[int, int], dict[str, Decimal]] = {}
    for lab_id, cat_id, approved, pending in spending_query.all():
        spending_by_lab_cat[(lab_id, cat_id)] = {
            "approved": _to_decimal(approved),
            "pending": _to_decimal(pending),
        }

    # ─── 3. Budgets per (lab, category) ───────────────────────────────
    budget_query = (
        db.query(
            Budget.lab_id,
            Budget.category_id,
            func.coalesce(func.sum(Budget.budget_amount), 0),
        )
        .join(LabGroup, LabGroup.lab_group_id == Budget.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .group_by(Budget.lab_id, Budget.category_id)
    )
    # Budget period scope. period_id: >0 = that fiscal year; 0 = all fiscal
    # years (sum — the "All time" view); None = current FY (default).
    if period_id == 0:
        budget_period = None
    elif period_id is not None:
        budget_period = period_id
    else:
        budget_period = _current_period_id(db)
    if budget_period is not None:
        budget_query = budget_query.filter(Budget.period_id == budget_period)
    if role_name == "teamlead":
        budget_query = budget_query.filter(
            Budget.lab_group_id == current_user.lab_group_id
        )
    elif role_name == "labic":
        assigned_lab_ids = [a.lab_id for a in current_user.lab_assignments]
        budget_query = budget_query.filter(Budget.lab_id.in_(assigned_lab_ids))

    budget_by_lab_cat: dict[tuple[int, int], Decimal] = {}
    for lab_id, cat_id, amount in budget_query.all():
        budget_by_lab_cat[(lab_id, cat_id)] = _to_decimal(amount)

    # ─── 4. Union of (lab, category) cells that exist (budget OR spend)
    all_cells: set[tuple[int, int]] = set(budget_by_lab_cat.keys()) | set(
        spending_by_lab_cat.keys()
    )

    # Group cells by lab_group_id → lab_id → list[category_id]
    by_group: dict[int, dict[int, list[int]]] = {}
    for lab_id, cat_id in all_cells:
        lg_id = lab_to_group.get(lab_id)
        if lg_id is None:
            continue
        if lab_group_names.get(lg_id) == "General":
            continue
        if role_name == "teamlead" and lg_id != current_user.lab_group_id:
            continue
        by_group.setdefault(lg_id, {}).setdefault(lab_id, []).append(cat_id)

    # ─── 5. Compose nested response, rolling up at each level ─────────
    result_groups: list[BreakdownLabGroup] = []
    for lg_id in sorted(by_group.keys()):
        labs_list: list[BreakdownLab] = []
        lg_budget = Decimal("0")
        lg_approved = Decimal("0")
        lg_pending = Decimal("0")

        for lab_id in sorted(by_group[lg_id].keys()):
            cats_list: list[BreakdownCategory] = []
            lab_budget = Decimal("0")
            lab_approved = Decimal("0")
            lab_pending = Decimal("0")

            # Sort with NULL category last; mixing int and None raises TypeError
            # under Python 3's sorted(), so key it explicitly.
            for cat_id in sorted(
                by_group[lg_id][lab_id], key=lambda c: (c is None, c or 0)
            ):
                cat_budget = budget_by_lab_cat.get((lab_id, cat_id), Decimal("0"))
                spending = spending_by_lab_cat.get((lab_id, cat_id), {})
                cat_approved = spending.get("approved", Decimal("0"))
                cat_pending = spending.get("pending", Decimal("0"))
                cat_available = cat_budget - cat_approved - cat_pending

                cats_list.append(
                    BreakdownCategory(
                        category_id=cat_id,
                        category_name=(
                            "Uncategorised"
                            if cat_id is None
                            else category_names.get(cat_id, "Unknown")
                        ),
                        budget_sgd=str(cat_budget),
                        actual_spend_sgd=str(cat_approved),
                        pending_sgd=str(cat_pending),
                        available_balance_sgd=str(cat_available),
                        utilisation_pct=_pct(cat_approved, cat_budget),
                        projected_utilisation_pct=_pct(
                            cat_approved + cat_pending, cat_budget
                        ),
                    )
                )
                lab_budget += cat_budget
                lab_approved += cat_approved
                lab_pending += cat_pending

            labs_list.append(
                BreakdownLab(
                    lab_id=lab_id,
                    lab_name=lab_names.get(lab_id, "Unknown"),
                    budget_sgd=str(lab_budget),
                    actual_spend_sgd=str(lab_approved),
                    pending_sgd=str(lab_pending),
                    available_balance_sgd=str(lab_budget - lab_approved - lab_pending),
                    utilisation_pct=_pct(lab_approved, lab_budget),
                    projected_utilisation_pct=_pct(
                        lab_approved + lab_pending, lab_budget
                    ),
                    categories=cats_list,
                )
            )
            lg_budget += lab_budget
            lg_approved += lab_approved
            lg_pending += lab_pending

        result_groups.append(
            BreakdownLabGroup(
                lab_group_id=lg_id,
                lab_group_name=lab_group_names.get(lg_id, "Unknown"),
                budget_sgd=str(lg_budget),
                actual_spend_sgd=str(lg_approved),
                pending_sgd=str(lg_pending),
                available_balance_sgd=str(lg_budget - lg_approved - lg_pending),
                utilisation_pct=_pct(lg_approved, lg_budget),
                projected_utilisation_pct=_pct(lg_approved + lg_pending, lg_budget),
                labs=labs_list,
            )
        )

    return BreakdownResponse(lab_groups=result_groups)


# ─── Monthly spend trend ─────────────────────────────────────────────────
class MonthlyPoint(BaseModel):
    month: str  # "YYYY-MM"
    amount: str


class MonthlyResponse(BaseModel):
    points: list[MonthlyPoint]


@router.get("/monthly", response_model=MonthlyResponse)
def get_monthly_spend(
    start_date: date | None = None,
    end_date: date | None = None,
    lab_group_id: int | None = None,
    lab_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> MonthlyResponse:
    """
    Approved committed spend grouped by month (YYYY-MM of the PR's request_date).
    Only Approved lines, real (non-General) lab groups. Optional date window +
    lab-group / lab filter. Role-scoped like the other dashboard endpoints; the
    frontend pads out the full fiscal-year months.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_DASHBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view dashboard spending.",
        )
    user_lab_ids = (
        [a.lab_id for a in current_user.lab_assignments] if role_name == "labic" else []
    )
    if role_name == "labic" and not user_lab_ids:
        return MonthlyResponse(points=[])
    if role_name == "teamlead" and not current_user.lab_group_id:
        return MonthlyResponse(points=[])

    month_expr = func.to_char(PurchaseRequest.request_date, "YYYY-MM")
    query = (
        db.query(
            month_expr.label("month"),
            func.coalesce(func.sum(PurchaseRequestLine.amount_gst), 0),
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(PurchaseRequestLine.pr_status.ilike("approved%"))
        .filter(LabGroup.lab_group_name != "General")
        .filter(PurchaseRequest.request_date.isnot(None))
        .group_by(month_expr)
        .order_by(month_expr)
    )
    if start_date is not None:
        query = query.filter(PurchaseRequest.request_date >= start_date)
    if end_date is not None:
        query = query.filter(PurchaseRequest.request_date <= end_date)
    if lab_group_id is not None:
        query = query.filter(Lab.lab_group_id == lab_group_id)
    if lab_id is not None:
        query = query.filter(PurchaseRequestLine.lab_id == lab_id)
    query = _apply_role_scope(query, current_user)

    points = [
        MonthlyPoint(month=month, amount=str(_to_decimal(amount)))
        for month, amount in query.all()
    ]
    return MonthlyResponse(points=points)


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return round(float((numerator / denominator) * 100), 1)


# ─── Excel export (W11-03) ───────────────────────────────────────────────
@router.get("/export")
def export_dashboard(
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    period_id: int | None = None,
    # Dashboard dropdowns. "all" (or omitted) means unfiltered.
    lab_group_id: int | None = None,
    lab_id: int | None = None,
    # Cover-block context only; never affects which rows are returned.
    custom_start: str = "",
    custom_end: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download the dashboard as a styled .xlsx workbook.

    Deliberately calls the very same functions the dashboard's own endpoints
    use — get_spending_summary / get_breakdown / get_monthly_spend — rather
    than re-querying. The role scoping and date handling therefore cannot
    drift from what the page shows, and a Team Lead's workbook can never
    contain another group's numbers.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_DASHBOARD_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can export the dashboard.",
        )

    spending = get_spending_summary(date_range, start_date, end_date, db, current_user)
    breakdown = get_breakdown(
        date_range, start_date, end_date, period_id, db, current_user
    )
    monthly = get_monthly_spend(
        start_date, end_date, lab_group_id, lab_id, db, current_user
    )
    lab_groups = get_lab_groups(period_id, db, current_user)

    groups = _filter_breakdown(breakdown.lab_groups, lab_group_id, lab_id)
    kpis = _dashboard_kpis(spending, lab_groups, groups, lab_group_id, lab_id)

    meta = DashboardMeta(
        generated_at=datetime.now(),
        generated_by_name=current_user.full_name or current_user.email,
        generated_by_email=current_user.email,
        role_label=DASHBOARD_ROLE_LABELS.get(role_name, role_name.title()),
        scope_label=_dashboard_scope_label(db, current_user, role_name),
        fy_label=_dashboard_fy_label(db, period_id),
        date_range_label=_dashboard_range_label(date_range, custom_start, custom_end),
        lab_group_label=_entity_label(
            lab_group_id,
            {g.lab_group_id: g.lab_group_name for g in groups},
            "All Lab Groups",
        ),
        lab_label=_entity_label(
            lab_id,
            {lab.lab_id: lab.lab_name for g in groups for lab in g.labs},
            "All labs",
        ),
    )

    stream = build_dashboard_workbook(meta, kpis, groups, groups, monthly.points)
    filename = f"Dashboard_{role_name}_{meta.generated_at.strftime('%Y%m%d_%H%M')}.xlsx"
    return StreamingResponse(
        stream,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
            ),
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


def _filter_breakdown(
    groups: list[BreakdownLabGroup], lab_group_id: int | None, lab_id: int | None
) -> list[BreakdownLabGroup]:
    """
    Apply the dashboard's Lab Group / Lab dropdowns to the breakdown tree.

    Mirrors DashboardPage.tsx: picking a lab narrows to that lab alone (and
    the group that owns it), picking a group narrows to that group.
    """
    if lab_id is not None:
        narrowed: list[BreakdownLabGroup] = []
        for group in groups:
            labs = [lab for lab in group.labs if lab.lab_id == lab_id]
            if labs:
                narrowed.append(group.model_copy(update={"labs": labs}))
        return narrowed
    if lab_group_id is not None:
        return [g for g in groups if g.lab_group_id == lab_group_id]
    return groups


def _dashboard_kpis(
    spending: SpendingSummary,
    lab_groups: list[Any],
    groups: list[BreakdownLabGroup],
    lab_group_id: int | None,
    lab_id: int | None,
) -> DashboardKpis:
    """
    Recreate the six KPI cards exactly as DashboardPage.tsx derives them.

    Total Budget comes from the System Config numbers (not the breakdown),
    while Actual and Pending come from the spending aggregate — except when a
    single lab is selected, where all three are read off that lab's row.
    """
    if lab_id is not None:
        lab = next(
            (lab for g in groups for lab in g.labs if lab.lab_id == lab_id), None
        )
        budget = _to_decimal(lab.budget_sgd) if lab else Decimal("0")
        actual = _to_decimal(lab.actual_spend_sgd) if lab else Decimal("0")
        pending = _to_decimal(lab.pending_sgd) if lab else Decimal("0")
    else:
        # get_lab_groups() hands back plain dicts (FastAPI only coerces them
        # to LabGroupOut at the response boundary), so index them as dicts —
        # a defaulted getattr here silently reads every budget as zero.
        if lab_group_id is None:
            budget = sum((_to_decimal(g["budget"]) for g in lab_groups), Decimal("0"))
            actual = _to_decimal(spending.total_actual_spend_sgd)
            pending = _to_decimal(spending.total_pending_sgd)
        else:
            match = next(
                (g for g in lab_groups if g["id"] == lab_group_id),
                None,
            )
            budget = _to_decimal(match["budget"]) if match else Decimal("0")
            key = str(lab_group_id)
            actual = _to_decimal(spending.by_lab_group.get(key, "0"))
            pending = _to_decimal(spending.pending_by_lab_group.get(key, "0"))

    available = budget - actual - pending
    return DashboardKpis(
        total_budget=float(budget),
        actual_spend=float(actual),
        pending=float(pending),
        available_balance=float(available),
        utilisation_pct=_pct(actual, budget),
        projected_utilisation_pct=_pct(actual + pending, budget),
    )


def _dashboard_scope_label(db: Session, user: User, role_name: str) -> str:
    if role_name == "teamlead":
        group = (
            db.query(LabGroup)
            .filter(LabGroup.lab_group_id == user.lab_group_id)
            .first()
        )
        name = group.lab_group_name if group else "Unassigned"
        return f"Lab Group: {name} (Team Lead scope)"
    if role_name == "labic":
        labs = db.query(Lab).filter(Lab.lab_id.in_(user.lab_ids)).all()
        names = ", ".join(sorted(lab.lab_name for lab in labs)) or "Unassigned"
        noun = "Labs" if len(labs) > 1 else "Lab"
        return f"{noun}: {names} (Lab IC scope)"
    return "All Lab Groups (Admin — full access)"


def _dashboard_fy_label(db: Session, period_id: int | None) -> str:
    if not period_id:
        return "All time"
    period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == period_id).first()
    if not period:
        return "All time"
    if period.start_date and period.end_date:
        return (
            f"{period.period_name} "
            f"({period.start_date.strftime('%d %b %Y')} – "
            f"{period.end_date.strftime('%d %b %Y')})"
        )
    return str(period.period_name)


def _dashboard_range_label(date_range: str, custom_start: str, custom_end: str) -> str:
    if custom_start or custom_end:
        return f"Custom: {custom_start or 'beginning'} to {custom_end or 'today'}"
    return DASHBOARD_RANGE_LABELS.get(date_range, "Whole year")


def _entity_label(entity_id: int | None, names: dict[int, str], fallback: str) -> str:
    if entity_id is None:
        return fallback
    return names.get(entity_id, str(entity_id))
