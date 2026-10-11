"""
PR Records API endpoints.

Read-only view of committed purchase requests (the official historical
record). Foundation for W9-02's 'Historical retrieval test' requirement
and a stepping stone for W11-03 reporting work.
"""

from datetime import date, datetime
from decimal import Decimal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.config import BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.models.auth import User
from app.services.records_insights_service import build_export_insights
from app.services.report_service import ReportMeta, build_pr_records_workbook
from app.utils.date_range import date_range_bounds

router = APIRouter(prefix="/api/records", tags=["Records"])

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# Lab IC may view PR Records, but scoped to their assigned labs only (see the
# query filter below): only PRs that have a line in one of their labs, and
# only those lines are returned.
ALLOWED_RECORDS_ROLES = {"admin", "teamlead", "labic"}

ROLE_LABELS = {
    "admin": "Admin",
    "teamlead": "Team Lead",
    "labic": "Lab IC",
}

# Mirror of the frontend FilterBar "Date Range" option labels.
DATE_RANGE_LABELS = {
    "all": "Whole year",
    "7d": "Last 7 days",
    "30d": "Last 30 days",
    "90d": "Last 90 days",
    "ytd": "Year to date",
}


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
    # PR Sub Date from the xlsx (ISO yyyy-mm-dd). Null if not populated.
    request_date: str | None
    lines: list[CommittedPRLine]


# ─── Endpoints ───────────────────────────────────────────────────────────
@router.get("/prs", response_model=list[CommittedPR])
def list_committed_prs(
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> list[CommittedPR]:
    """
    Return all committed purchase requests (with their lines).

    Role scoping:
      - Admin     → every committed PR.
      - Team Lead → only PRs whose lab_group_id matches their lab_group_id.
      - Lab IC    → only PRs that have a line in one of their assigned labs, and only
        those lines are returned (other labs' lines in the same PR are hidden,
        and the PR total is recomputed from the visible lines).

    Date filtering (W11-03) is on ``request_date`` (the xlsx "PR Sub Date"):
      - ``start_date`` / ``end_date`` — an explicit custom range. If either is
        given it OVERRIDES the preset.
      - ``date_range`` — a preset (all / fy / 7d / 30d / 90d / ytd), used only
        when no custom dates are supplied.
    When any bound is active, PRs with no request_date drop out (the >= / <=
    comparison fails on NULL).

    Sorted most-recently-updated first so the freshest data sits at the top.
    """
    role_name = _require_records_role(current_user)
    return _scoped_committed_prs(
        db, current_user, role_name, date_range, start_date, end_date
    )


@router.get("/export")
def export_committed_prs(
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    # The PR Records page narrows the server result further, client-side, with
    # a free-text search and (Admin only) a Lab Group dropdown. Both are passed
    # through here so the workbook matches the screen exactly.
    search: str = "",
    lab_group: str = "all",
    # Cover-block context only — never affects which rows are returned.
    period_id: int | None = None,
    custom_start: str = "",
    custom_end: str = "",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """
    Download the currently-visible PR Records as a styled .xlsx workbook.

    Reuses the exact same role-scoped query as ``/prs`` — a Team Lead can no
    more export another group's PRs than they can view them — then applies the
    page's client-side search / Lab Group filters so the file is a faithful
    copy of what the user is looking at.
    """
    role_name = _require_records_role(current_user)
    prs = _scoped_committed_prs(
        db, current_user, role_name, date_range, start_date, end_date
    )
    prs = _apply_view_filters(prs, search, lab_group)

    meta = ReportMeta(
        generated_at=datetime.now(),
        generated_by_name=current_user.full_name or current_user.email,
        generated_by_email=current_user.email,
        role_label=ROLE_LABELS.get(role_name, role_name.title()),
        scope_label=_scope_label(db, current_user, role_name),
        fy_label=_fy_label(db, period_id),
        date_range_label=_date_range_label(date_range, custom_start, custom_end),
        search_label=f'"{search.strip()}"' if search.strip() else "None",
        lab_group_label=_lab_group_label(prs, lab_group, role_name),
    )

    # Extra sheets (trail / change history / budget impact) — built from the
    # same scoped PR list, so they can't show anything the page doesn't.
    insights = build_export_insights(db, prs, role_name)
    stream = build_pr_records_workbook(prs, meta, insights)
    filename = (
        f"PR_Records_{role_name}_{meta.generated_at.strftime('%Y%m%d_%H%M')}.xlsx"
    )
    return StreamingResponse(
        stream,
        media_type=XLSX_MEDIA_TYPE,
        headers={
            "Content-Disposition": (
                f"attachment; filename={filename}; filename*=UTF-8''{quote(filename)}"
            ),
            # The browser fetch needs to read the name back off the response.
            "Access-Control-Expose-Headers": "Content-Disposition",
        },
    )


# ─── Query ───────────────────────────────────────────────────────────────
def _scoped_committed_prs(
    db: Session,
    current_user: User,
    role_name: str,
    date_range: str,
    start_date: date | None,
    end_date: date | None,
) -> list[CommittedPR]:
    """Role-scoped, date-filtered committed PRs. Shared by /prs and /export."""
    user_lab_ids = current_user.lab_ids if role_name == "labic" else []
    query = db.query(PurchaseRequest)
    if role_name == "teamlead":
        if not current_user.lab_group_id:
            return []
        query = query.filter(PurchaseRequest.lab_group_id == current_user.lab_group_id)
    elif role_name == "labic":
        if not user_lab_ids:
            return []
        # Match PRs that contain lines for ANY of the Lab IC's assigned labs
        query = query.filter(
            PurchaseRequest.lines.any(PurchaseRequestLine.lab_id.in_(user_lab_ids))
        )

    # Custom range wins; otherwise fall back to the preset. date_range_bounds
    # handles "fy" (both ends) as well as the relative windows (lower bound).
    if start_date is not None or end_date is not None:
        start, end = start_date, end_date
    else:
        start, end = date_range_bounds(date_range)
    if start is not None:
        query = query.filter(PurchaseRequest.request_date >= start)
    if end is not None:
        query = query.filter(PurchaseRequest.request_date <= end)

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
    lines_query = db.query(PurchaseRequestLine).filter(
        PurchaseRequestLine.pr_id.in_(pr_ids)
    )
    # Lab IC only sees their own labs' lines within each PR.
    if role_name == "labic":
        lines_query = lines_query.filter(PurchaseRequestLine.lab_id.in_(user_lab_ids))
    all_lines = lines_query.order_by(
        PurchaseRequestLine.pr_id, PurchaseRequestLine.line_no
    ).all()
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
            grand_total_sgd=_pr_grand_total(
                pr, lines_by_pr.get(pr.pr_id, []), role_name
            ),
            lab_group_name=group_names.get(pr.lab_group_id, "General"),
            latest_batch_id=pr.latest_batch_id,
            updated_at=pr.updated_at,
            status="committed",
            pr_status=pr.pr_status,
            request_date=pr.request_date.isoformat() if pr.request_date else None,
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


def _apply_view_filters(
    prs: list[CommittedPR], search: str, lab_group: str
) -> list[CommittedPR]:
    """
    Reproduce the PR Records page's client-side filters.

    Mirrors RecordsPage.tsx ``filteredRecords``: the Lab Group dropdown
    (whose option value is the lowercased group name) and a case-insensitive
    substring search over the PR header fields plus each line's item
    description, lab name and status.
    """
    query = search.strip().lower()
    group = lab_group.strip().lower()

    def matches(pr: CommittedPR) -> bool:
        if group and group != "all" and (pr.lab_group_name or "").lower() != group:
            return False
        if not query:
            return True
        for field in (
            pr.source_pr_number,
            pr.requestor_name,
            pr.wbs_code,
            pr.lab_group_name,
        ):
            if field and query in field.lower():
                return True
        return any(
            (line.item_description and query in line.item_description.lower())
            or (line.lab_name and query in line.lab_name.lower())
            or (line.pr_status and query in line.pr_status.lower())
            for line in pr.lines
        )

    return [pr for pr in prs if matches(pr)]


# ─── Helpers ─────────────────────────────────────────────────────────────
def _require_records_role(user: User) -> str:
    role_name = _role_name(user)
    if role_name not in ALLOWED_RECORDS_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Admin or Team Lead can view PR Records.",
        )
    return role_name


def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()


def _pr_grand_total(pr, visible_lines, role_name: str) -> str:
    """PR total to display.

    For Lab IC we only surface their own lab's lines, so the stored whole-PR
    grand total (which may include other labs' lines within the same group)
    would over-report. Recompute from the visible lines instead so the total
    matches what the Lab IC can actually see.
    """
    if role_name == "labic":
        total = sum((line.amount_gst or Decimal("0")) for line in visible_lines)
        return str(total)
    return str(pr.grand_total_sgd) if pr.grand_total_sgd is not None else "0"


# ─── Report cover labels ─────────────────────────────────────────────────
def _scope_label(db: Session, user: User, role_name: str) -> str:
    """Describe, in the report header, what this role was allowed to see."""
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
        return f"{noun}: {names} (Lab IC scope — own labs' lines only)"
    return "All Lab Groups (Admin — full access)"


def _fy_label(db: Session, period_id: int | None) -> str:
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


def _date_range_label(date_range: str, custom_start: str, custom_end: str) -> str:
    if custom_start or custom_end:
        start = custom_start or "beginning"
        end = custom_end or "today"
        return f"Custom: {start} to {end}"
    return DATE_RANGE_LABELS.get(date_range, "Whole year")


def _lab_group_label(prs: list[CommittedPR], lab_group: str, role_name: str) -> str:
    if role_name != "admin":
        return "Not applicable for this role"
    if not lab_group or lab_group.lower() == "all":
        return "All Lab Groups"
    # The dropdown value is the lowercased group name; recover the real casing.
    for pr in prs:
        if (pr.lab_group_name or "").lower() == lab_group.lower():
            return pr.lab_group_name
    return lab_group
