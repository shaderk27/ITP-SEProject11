from datetime import date, datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from app.api.config import get_or_create_current_period
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine, UploadBatch
from app.utils.date_range import date_range_bounds

router = APIRouter(prefix="/api/alerts", tags=["Alerts"])

ALLOWED_ALERT_ROLES = {"admin", "teamlead", "labic"}


# ─── Response Shapes ─────────────────────────────────────────────────────
class DrilldownPRLine(BaseModel):
    pr_line_id: int
    pr_id: int
    source_pr_number: str
    line_no: int | None
    item_description: str
    requestor_name: str
    request_date: str | None
    amount_gst: str
    pr_status: str | None
    latest_batch_id: int | None
    is_triggering_line: bool


class DrilldownCategory(BaseModel):
    category_id: int | None
    category_name: str
    budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    committed_spend_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float
    pr_lines: list[DrilldownPRLine]


class DrilldownLab(BaseModel):
    lab_id: int
    lab_code: str | None
    lab_name: str
    budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    committed_spend_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float
    threshold_reached: int | None
    triggering_batch_id: int | None
    categories: list[DrilldownCategory]


class DrilldownLabGroup(BaseModel):
    lab_group_id: int
    lab_group_name: str
    wbs_code: str | None
    envelope_budget_sgd: str
    allocated_lab_budget_sgd: str
    actual_spend_sgd: str
    pending_sgd: str
    committed_spend_sgd: str
    available_balance_sgd: str
    utilisation_pct: float
    projected_utilisation_pct: float
    threshold_reached: int | None
    triggering_batch_id: int | None
    labs: list[DrilldownLab]


class AlertDrilldownResponse(BaseModel):
    lab_groups: list[DrilldownLabGroup]


# ─── Helpers ─────────────────────────────────────────────────────────────
def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return round(float((numerator / denominator) * 100), 1)


def _threshold_level(utilisation_pct: float) -> int | None:
    if utilisation_pct >= 100:
        return 100
    if utilisation_pct >= 95:
        return 95
    if utilisation_pct >= 80:
        return 80
    if utilisation_pct >= 50:
        return 50
    return None


def _to_timestamp(value: Any) -> float:
    if value is None:
        return 0.0
    if isinstance(value, datetime):
        return value.timestamp()
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day).timestamp()
    return 0.0


def _chronological_sort_key(
    item: (
        tuple[PurchaseRequestLine, PurchaseRequest, UploadBatch | None]
        | tuple[PurchaseRequestLine, PurchaseRequest]
    ),
) -> tuple[float, int, float, int, int, int]:
    """
    Order PR lines by UploadBatch commit/upload chronology first, then PR and line order.
    """
    pr_line = item[0]
    pr_header = item[1]
    batch = item[2] if len(item) > 2 else None

    batch_commit_ts = _to_timestamp(
        getattr(batch, "processed_at", None) or getattr(batch, "uploaded_at", None)
    )
    batch_id = (
        getattr(batch, "batch_id", None)
        or getattr(pr_header, "latest_batch_id", None)
        or 0
    )
    pr_created_ts = _to_timestamp(
        getattr(pr_header, "created_at", None)
        or getattr(pr_header, "request_date", None)
    )

    return (
        batch_commit_ts,
        batch_id,
        pr_created_ts,
        pr_header.pr_id or 0,
        pr_line.line_no or 0,
        pr_line.pr_line_id or 0,
    )


def _find_threshold_crossing(
    items: list[tuple[PurchaseRequestLine, PurchaseRequest, UploadBatch | None]],
    budget: Decimal,
    threshold: int | None,
) -> tuple[int | None, int | None]:
    """
    Process contributing PR lines in UploadBatch commit chronology and identify
    the exact batch and PR line where cumulative committed spend first crossed `threshold`.
    """
    if threshold is None or budget <= 0 or not items:
        return None, None

    sorted_items = sorted(items, key=_chronological_sort_key)
    running_spend = Decimal("0")
    for item in sorted_items:
        pr_line = item[0]
        pr_header = item[1]
        batch = item[2] if len(item) > 2 else None
        running_spend += _to_decimal(pr_line.amount_gst)
        if _pct(running_spend, budget) >= threshold:
            trigger_batch_id = (
                getattr(batch, "batch_id", None)
                if batch is not None
                else pr_header.latest_batch_id
            )
            return trigger_batch_id, pr_line.pr_line_id

    return None, None


# ─── W17-01B Alert Traceability Drill-Down Endpoint ──────────────────────
@router.get("/drilldown", response_model=AlertDrilldownResponse)
def get_alert_drilldown(
    lab_group_id: int | None = None,
    lab_id: int | None = None,
    category_id: int | None = None,
    period_id: int | None = None,
    date_range: str = "all",
    start_date: date | None = None,
    end_date: date | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> AlertDrilldownResponse:
    """
    W17-01B Alert Traceability Flow:
      Lab Group alert → contributing Labs → Spending Categories → triggering/contributing PR lines.
    """
    role_name = _role_name(current_user)
    if role_name not in ALLOWED_ALERT_ROLES:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access denied.",
        )

    user_lab_ids = (
        [a.lab_id for a in current_user.lab_assignments] if role_name == "labic" else []
    )

    # 1. Strict RBAC Scope Validation
    if role_name == "teamlead":
        if not current_user.lab_group_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Team Lead is not assigned to a lab group.",
            )
        if lab_group_id is not None and lab_group_id != current_user.lab_group_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot drill down into another Lab Group.",
            )
        if lab_id is not None:
            target_lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
            if not target_lab or target_lab.lab_group_id != current_user.lab_group_id:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot drill down into a Lab outside your Lab Group.",
                )
    elif role_name == "labic":
        if not user_lab_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Lab IC has no assigned labs.",
            )
        if lab_id is not None and lab_id not in user_lab_ids:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Cannot drill down into an unassigned Lab.",
            )
        if lab_group_id is not None:
            allowed_groups = {
                row[0]
                for row in db.query(Lab.lab_group_id)
                .filter(Lab.lab_id.in_(user_lab_ids))
                .all()
                if row[0] is not None
            }
            if lab_group_id not in allowed_groups:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Cannot drill down into an unassigned Lab Group.",
                )

    # 2. Resolve Fiscal Period & Date Bounds (reconciled with config.py)
    target_period_id = (
        period_id if period_id is not None else get_or_create_current_period(db)
    )
    active_period = (
        db.query(BudgetPeriod)
        .filter(BudgetPeriod.period_id == target_period_id)
        .first()
        if target_period_id
        else None
    )

    if start_date is not None or end_date is not None:
        start, end = start_date, end_date
    elif date_range != "all":
        start, end = date_range_bounds(date_range)
    elif active_period:
        start, end = active_period.start_date, active_period.end_date
    else:
        start, end = None, None

    # 3. Fetch Scoped Lab Groups, Labs, and Categories
    groups_query = db.query(LabGroup).filter(LabGroup.lab_group_name != "General")
    if lab_group_id is not None:
        groups_query = groups_query.filter(LabGroup.lab_group_id == lab_group_id)
    elif lab_id is not None:
        groups_query = (
            groups_query.join(Lab, Lab.lab_group_id == LabGroup.lab_group_id)
            .filter(Lab.lab_id == lab_id)
            .distinct()
        )
    elif role_name == "teamlead":
        groups_query = groups_query.filter(
            LabGroup.lab_group_id == current_user.lab_group_id
        )
    elif role_name == "labic":
        groups_query = (
            groups_query.join(Lab, Lab.lab_group_id == LabGroup.lab_group_id)
            .filter(Lab.lab_id.in_(user_lab_ids))
            .distinct()
        )
    groups = groups_query.order_by(LabGroup.lab_group_id).all()
    if not groups:
        return AlertDrilldownResponse(lab_groups=[])

    group_ids = [g.lab_group_id for g in groups]

    labs_query = db.query(Lab).filter(Lab.lab_group_id.in_(group_ids))
    if lab_id is not None:
        labs_query = labs_query.filter(Lab.lab_id == lab_id)
    if role_name == "labic":
        labs_query = labs_query.filter(Lab.lab_id.in_(user_lab_ids))
    labs = labs_query.order_by(Lab.lab_id).all()
    lab_ids = [lab.lab_id for lab in labs]

    category_names = {
        c.category_id: c.category_name for c in db.query(SpendingCategory).all()
    }

    # 4. Fetch Budgets (Group Envelopes + Lab Category Budgets)
    envelope_by_group: dict[int, Decimal] = {}
    env_q = db.query(
        Budget.lab_group_id, func.coalesce(func.sum(Budget.budget_amount), 0)
    ).filter(Budget.lab_group_id.in_(group_ids), Budget.lab_id.is_(None))
    if target_period_id:
        env_q = env_q.filter(Budget.period_id == target_period_id)
    for gid, amt in env_q.group_by(Budget.lab_group_id).all():
        envelope_by_group[gid] = _to_decimal(amt)

    budget_by_lab_cat: dict[tuple[int, int | None], Decimal] = {}
    if lab_ids:
        cat_b_q = db.query(
            Budget.lab_id,
            Budget.category_id,
            func.coalesce(func.sum(Budget.budget_amount), 0),
        ).filter(Budget.lab_id.in_(lab_ids))
        if target_period_id:
            cat_b_q = cat_b_q.filter(Budget.period_id == target_period_id)
        if category_id is not None:
            cat_b_q = cat_b_q.filter(Budget.category_id == category_id)
        for lid, cid, amt in cat_b_q.group_by(Budget.lab_id, Budget.category_id).all():
            budget_by_lab_cat[(lid, cid)] = _to_decimal(amt)

    # 5. Fetch Contributing PR Lines with UploadBatch for Commit Chronology
    lines_by_lab_cat: dict[
        tuple[int, int | None],
        list[tuple[PurchaseRequestLine, PurchaseRequest, UploadBatch | None]],
    ] = {}

    if lab_ids:
        lines_q = (
            db.query(PurchaseRequestLine, PurchaseRequest, UploadBatch)
            .join(
                PurchaseRequest,
                PurchaseRequest.pr_id == PurchaseRequestLine.pr_id,
            )
            .outerjoin(
                UploadBatch,
                UploadBatch.batch_id == PurchaseRequest.latest_batch_id,
            )
            .filter(
                PurchaseRequestLine.lab_id.in_(lab_ids),
                or_(
                    PurchaseRequestLine.pr_status.is_(None),
                    and_(
                        PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                        PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                    ),
                ),
            )
        )
        if start is not None:
            lines_q = lines_q.filter(PurchaseRequest.request_date >= start)
        if end is not None:
            lines_q = lines_q.filter(PurchaseRequest.request_date <= end)
        if category_id is not None:
            lines_q = lines_q.filter(PurchaseRequestLine.category_id == category_id)

        for pr_line, pr_header, batch in lines_q.order_by(
            PurchaseRequest.request_date.desc(),
            PurchaseRequest.pr_id.desc(),
            PurchaseRequestLine.line_no.asc(),
        ).all():
            lid = pr_line.lab_id
            cid = pr_line.category_id
            lines_by_lab_cat.setdefault((lid, cid), []).append(
                (pr_line, pr_header, batch)
            )

    # 6. Assemble 3-Level Traceability Hierarchy
    labs_by_group: dict[int, list[Lab]] = {}
    for lab in labs:
        if lab.lab_group_id is not None:
            labs_by_group.setdefault(lab.lab_group_id, []).append(lab)

    out_groups: list[DrilldownLabGroup] = []
    for g in groups:
        gid = g.lab_group_id
        group_labs = labs_by_group.get(gid, [])
        out_labs: list[DrilldownLab] = []
        group_all_lines: list[
            tuple[PurchaseRequestLine, PurchaseRequest, UploadBatch | None]
        ] = []

        lg_allocated_budget = Decimal("0")
        lg_actual = Decimal("0")
        lg_pending = Decimal("0")
        lg_committed = Decimal("0")

        for lab in group_labs:
            lid = lab.lab_id
            cat_keys = {
                cid
                for (k_lid, cid) in (
                    set(budget_by_lab_cat.keys()) | set(lines_by_lab_cat.keys())
                )
                if k_lid == lid
            }

            lab_budget = Decimal("0")
            lab_actual = Decimal("0")
            lab_pending = Decimal("0")
            lab_committed = Decimal("0")
            lab_all_lines: list[
                tuple[PurchaseRequestLine, PurchaseRequest, UploadBatch | None]
            ] = []

            for cid in cat_keys:
                lab_budget += budget_by_lab_cat.get((lid, cid), Decimal("0"))
                cat_items = lines_by_lab_cat.get((lid, cid), [])
                lab_all_lines.extend(cat_items)
                group_all_lines.extend(cat_items)
                for pr_line, _, _ in cat_items:
                    amt = _to_decimal(pr_line.amount_gst)
                    status_lower = (pr_line.pr_status or "").lower()
                    if status_lower.startswith("approved"):
                        lab_actual += amt
                    elif status_lower.startswith("pending"):
                        lab_pending += amt
                    lab_committed += amt

            lab_util_pct = _pct(lab_committed, lab_budget)
            lab_threshold = _threshold_level(lab_util_pct)
            lab_trigger_batch, lab_trigger_line_id = _find_threshold_crossing(
                lab_all_lines, lab_budget, lab_threshold
            )

            out_cats: list[DrilldownCategory] = []
            for cid in sorted(cat_keys, key=lambda c: (c is None, c or 0)):
                cat_budget = budget_by_lab_cat.get((lid, cid), Decimal("0"))
                cat_actual = Decimal("0")
                cat_pending = Decimal("0")
                cat_committed = Decimal("0")
                out_lines: list[DrilldownPRLine] = []

                for pr_line, pr_header, _ in lines_by_lab_cat.get((lid, cid), []):
                    amt = _to_decimal(pr_line.amount_gst)
                    status_lower = (pr_line.pr_status or "").lower()
                    if status_lower.startswith("approved"):
                        cat_actual += amt
                    elif status_lower.startswith("pending"):
                        cat_pending += amt
                    cat_committed += amt

                    # Mark ONLY the exact line that crossed the threshold
                    is_triggering = (
                        lab_trigger_line_id is not None
                        and pr_line.pr_line_id == lab_trigger_line_id
                    )

                    out_lines.append(
                        DrilldownPRLine(
                            pr_line_id=pr_line.pr_line_id,
                            pr_id=pr_header.pr_id,
                            source_pr_number=pr_header.source_pr_number,
                            line_no=pr_line.line_no,
                            item_description=pr_line.item_description or "",
                            requestor_name=pr_header.requestor_name or "",
                            request_date=(
                                pr_header.request_date.isoformat()
                                if pr_header.request_date
                                else None
                            ),
                            amount_gst=str(amt),
                            pr_status=pr_line.pr_status,
                            latest_batch_id=pr_header.latest_batch_id,
                            is_triggering_line=is_triggering,
                        )
                    )

                out_cats.append(
                    DrilldownCategory(
                        category_id=cid,
                        category_name=(
                            "Uncategorised"
                            if cid is None
                            else category_names.get(cid, "Unknown")
                        ),
                        budget_sgd=str(cat_budget),
                        actual_spend_sgd=str(cat_actual),
                        pending_sgd=str(cat_pending),
                        committed_spend_sgd=str(cat_committed),
                        available_balance_sgd=str(cat_budget - cat_committed),
                        utilisation_pct=_pct(cat_actual, cat_budget),
                        projected_utilisation_pct=_pct(cat_committed, cat_budget),
                        pr_lines=out_lines,
                    )
                )

            out_labs.append(
                DrilldownLab(
                    lab_id=lid,
                    lab_code=lab.lab_code,
                    lab_name=lab.lab_name,
                    budget_sgd=str(lab_budget),
                    actual_spend_sgd=str(lab_actual),
                    pending_sgd=str(lab_pending),
                    committed_spend_sgd=str(lab_committed),
                    available_balance_sgd=str(lab_budget - lab_committed),
                    utilisation_pct=_pct(lab_actual, lab_budget),
                    projected_utilisation_pct=lab_util_pct,
                    threshold_reached=lab_threshold,
                    triggering_batch_id=lab_trigger_batch,
                    categories=out_cats,
                )
            )
            lg_allocated_budget += lab_budget
            lg_actual += lab_actual
            lg_pending += lab_pending
            lg_committed += lab_committed

        env_budget = envelope_by_group.get(gid, lg_allocated_budget)
        lg_util_pct = _pct(lg_committed, env_budget)
        lg_threshold = _threshold_level(lg_util_pct)
        lg_trigger_batch, lg_trigger_line_id = _find_threshold_crossing(
            group_all_lines, env_budget, lg_threshold
        )

        # If a lab itself is below 50% but is displayed because its parent group
        # crossed a threshold, mark only the exact group-triggering line.
        if lg_trigger_line_id is not None:
            for d_lab in out_labs:
                if d_lab.threshold_reached is None:
                    for d_cat in d_lab.categories:
                        for d_line in d_cat.pr_lines:
                            if d_line.pr_line_id == lg_trigger_line_id:
                                d_line.is_triggering_line = True

        out_groups.append(
            DrilldownLabGroup(
                lab_group_id=gid,
                lab_group_name=g.lab_group_name,
                wbs_code=g.wbs_code,
                envelope_budget_sgd=str(env_budget),
                allocated_lab_budget_sgd=str(lg_allocated_budget),
                actual_spend_sgd=str(lg_actual),
                pending_sgd=str(lg_pending),
                committed_spend_sgd=str(lg_committed),
                available_balance_sgd=str(env_budget - lg_committed),
                utilisation_pct=_pct(lg_actual, env_budget),
                projected_utilisation_pct=lg_util_pct,
                threshold_reached=lg_threshold,
                triggering_batch_id=lg_trigger_batch,
                labs=out_labs,
            )
        )

    return AlertDrilldownResponse(lab_groups=out_groups)