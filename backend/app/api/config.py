from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import func, or_, and_
from typing import List
from datetime import date
from sqlalchemy.exc import IntegrityError

from app.models.config import (
    LabGroup,
    Lab,
    SpendingCategory,
    Budget,
    BudgetPeriod,
    LabGroupOut,
    LabOut,
    CategoryOut,
    LabGroupCreate,
    LabCreate,
    CategoryCreate,
    LabIcAssignment,
)
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.services.audit_service import log_audit_action

from app.services.threshold_service import (
    check_and_notify_lab_thresholds,
    check_and_notify_lab_group_thresholds,
)
from app.models.staging import PurchaseRequestLine, PurchaseRequest

router = APIRouter(prefix="/api/config", tags=["Configuration"])


# ==============================
# AUTOMATIC FY PERIOD GENERATOR
# ==============================
def get_or_create_current_period(db: Session) -> int:
    today = date.today()
    if today.month < 4:
        start_year = today.year - 1
    else:
        start_year = today.year

    period_name = f"FY{start_year}"

    existing_period = (
        db.query(BudgetPeriod).filter(BudgetPeriod.period_name == period_name).first()
    )
    if existing_period:
        return existing_period.period_id

    new_period = BudgetPeriod(
        period_name=period_name,
        year_no=start_year,
        start_date=date(start_year, 4, 1),
        end_date=date(start_year + 1, 3, 31),
    )
    db.add(new_period)
    db.commit()
    db.refresh(new_period)

    return new_period.period_id


def _period_out(p: BudgetPeriod) -> dict:
    return {
        "id": p.period_id,
        "name": p.period_name,
        "year": p.year_no,
        "start_date": p.start_date.isoformat() if p.start_date else None,
        "end_date": p.end_date.isoformat() if p.end_date else None,
        "is_closed": p.is_closed,
    }


def _active_pr_status_filter():
    return or_(
        PurchaseRequestLine.pr_status.is_(None),
        and_(
            PurchaseRequestLine.pr_status.not_ilike("%reject%"),
            PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
        ),
    )


# ==============================
# FISCAL YEAR (BUDGET PERIOD) API
# ==============================
class PeriodCreate(BaseModel):
    year: int


@router.get("/periods")
def list_periods(db: Session = Depends(get_db)):
    get_or_create_current_period(db)
    periods = db.query(BudgetPeriod).order_by(BudgetPeriod.year_no.desc()).all()
    return [_period_out(p) for p in periods]


@router.post("/periods")
def create_period(
    payload: PeriodCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    year = payload.year
    if year < 2000 or year > 2100:
        raise HTTPException(
            status_code=400, detail="Year must be between 2000 and 2100."
        )
    name = f"FY{year}"
    existing = db.query(BudgetPeriod).filter(BudgetPeriod.period_name == name).first()
    if existing:
        raise HTTPException(status_code=400, detail=f"{name} already exists.")
    period = BudgetPeriod(
        period_name=name,
        year_no=year,
        start_date=date(year, 4, 1),
        end_date=date(year + 1, 3, 31),
    )
    db.add(period)
    db.commit()
    db.refresh(period)

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="CREATE",
        entity_name="FiscalYear",
        record_id=str(period.period_id),
        new_value={"name": period.period_name, "year": period.year_no},
        request=request,
    )

    return _period_out(period)


# ==============================
# LAB GROUPS API
# ==============================
@router.get("/labgroups", response_model=List[LabGroupOut])
def get_lab_groups(
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = (
        (current_user.role.role_name if current_user.role else "").lower().strip()
    )
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    query = db.query(LabGroup)
    if role_name == "teamlead":
        if not current_user.lab_group_id:
            return []
        query = query.filter(LabGroup.lab_group_id == current_user.lab_group_id)
    elif role_name == "labic":
        user_lab_ids = [a.lab_id for a in current_user.lab_assignments]
        if not user_lab_ids:
            return []
        user_lab_group_ids = (
            db.query(Lab.lab_group_id)
            .filter(Lab.lab_id.in_(user_lab_ids), Lab.lab_group_id.isnot(None))
            .distinct()
            .all()
        )
        group_ids = [gid[0] for gid in user_lab_group_ids if gid[0]]
        if not group_ids:
            return []
        query = query.filter(LabGroup.lab_group_id.in_(group_ids))
    elif role_name != "admin":
        return []

    groups = query.all()
    result = []
    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()

    for g in groups:
        total_budget_envelope = float(
            db.query(func.sum(Budget.budget_amount))
            .filter(
                Budget.lab_group_id == g.lab_group_id,
                Budget.lab_id.is_(None),
                Budget.period_id == pid,
            )
            .scalar()
            or 0
        )

        allocated_to_labs = float(
            db.query(func.sum(Budget.budget_amount))
            .filter(
                Budget.lab_group_id == g.lab_group_id,
                Budget.lab_id.isnot(None),
                Budget.period_id == pid,
            )
            .scalar()
            or 0
        )

        if active_period:
            total_spent = float(
                db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(
                    PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id
                )
                .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
                .filter(
                    Lab.lab_group_id == g.lab_group_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    _active_pr_status_filter(),
                )
                .scalar()
                or 0
            )
        else:
            total_spent = 0.0

        result.append(
            {
                "id": g.lab_group_id,
                "name": g.lab_group_name,
                "wbs_code": g.wbs_code or "",
                "description": g.description or "",
                "budget": total_budget_envelope,
                "allocated_to_labs": allocated_to_labs,
                "unallocated": total_budget_envelope - allocated_to_labs,
                "spent": total_spent,
                "threshold": 80,
            }
        )
    return result


@router.post("/labgroups", response_model=LabGroupOut)
def create_lab_group(
    group: LabGroupCreate,
    request: Request,
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    existing_wbs = (
        db.query(LabGroup)
        .filter(func.lower(LabGroup.wbs_code) == group.wbs_code.lower())
        .first()
    )
    if existing_wbs:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create Lab Group: The WBS Prefix '{group.wbs_code}' is already in use by another group.",
        )

    new_group = LabGroup(
        lab_group_name=group.name,
        wbs_code=group.wbs_code,
        description=group.description,
    )
    db.add(new_group)
    db.flush()

    if group.budget > 0:
        envelope = Budget(
            period_id=pid,
            lab_group_id=new_group.lab_group_id,
            lab_id=None,
            category_id=None,
            budget_amount=group.budget,
            updated_at=func.now(),
        )
        db.add(envelope)

    if hasattr(group, "assigned_lab_ids") and group.assigned_lab_ids:
        labs_to_update = (
            db.query(Lab).filter(Lab.lab_id.in_(group.assigned_lab_ids)).all()
        )
        for lab in labs_to_update:
            lab.lab_group_id = new_group.lab_group_id

        budgets_to_update = (
            db.query(Budget).filter(Budget.lab_id.in_(group.assigned_lab_ids)).all()
        )
        for b in budgets_to_update:
            b.lab_group_id = new_group.lab_group_id

    db.commit()
    db.refresh(new_group)

    allocated = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == new_group.lab_group_id,
            Budget.lab_id.isnot(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="CREATE",
        entity_name="LabGroup",
        record_id=str(new_group.lab_group_id),
        new_value={
            "name": new_group.lab_group_name,
            "wbs_code": new_group.wbs_code,
            "budget": float(group.budget),
        },
        request=request,
    )

    return {
        "id": new_group.lab_group_id,
        "name": new_group.lab_group_name,
        "wbs_code": new_group.wbs_code,
        "description": new_group.description,
        "budget": float(group.budget),
        "allocated_to_labs": allocated,
        "unallocated": float(group.budget) - allocated,
        "spent": 0.0,
        "threshold": 80,
    }


@router.put("/labgroups/{group_id}", response_model=LabGroupOut)
def update_lab_group(
    group_id: int,
    group: LabGroupCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404)

    pid = period_id if period_id is not None else get_or_create_current_period(db)

    existing_wbs = (
        db.query(LabGroup)
        .filter(
            func.lower(LabGroup.wbs_code) == group.wbs_code.lower(),
            LabGroup.lab_group_id != group_id,
        )
        .first()
    )
    if existing_wbs:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update Lab Group: The WBS Prefix '{group.wbs_code}' is already in use by another group.",
        )

    # Calculate current allocations (including any newly assigned orphaned labs)
    current_allocated = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == group_id,
            Budget.lab_id.isnot(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )
    newly_assigned_allocated = 0.0
    if hasattr(group, "assigned_lab_ids") and group.assigned_lab_ids:
        newly_assigned_allocated = float(
            db.query(func.sum(Budget.budget_amount))
            .filter(
                Budget.lab_id.in_(group.assigned_lab_ids),
                Budget.lab_group_id != group_id,
                Budget.period_id == pid,
            )
            .scalar()
            or 0
        )
    total_allocated_to_labs = current_allocated + newly_assigned_allocated

    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()
    if active_period:
        total_spent = float(
            db.query(func.sum(PurchaseRequestLine.amount_gst))
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
            .filter(
                Lab.lab_group_id == group_id,
                PurchaseRequest.request_date >= active_period.start_date,
                PurchaseRequest.request_date <= active_period.end_date,
                _active_pr_status_filter(),
            )
            .scalar()
            or 0
        )
    else:
        total_spent = 0.0

    requested_group_budget = float(group.budget)

    # Guard 1: Cannot reduce Lab Group envelope below what is already allocated to labs
    if requested_group_budget + 1e-6 < total_allocated_to_labs:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot set Lab Group budget to ${requested_group_budget:,.2f}: "
                f"${total_allocated_to_labs:,.2f} is already allocated to labs in this group. "
                "Please reduce lab budget allocations first."
            ),
        )

    # Guard 2: Cannot reduce Lab Group envelope below what has already been spent
    if requested_group_budget + 1e-6 < total_spent:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot set Lab Group budget to ${requested_group_budget:,.2f}: "
                f"${total_spent:,.2f} has already been spent/utilised in this Lab Group."
            ),
        )

    envelope = (
        db.query(Budget)
        .filter(
            Budget.lab_group_id == group_id,
            Budget.lab_id.is_(None),
            Budget.period_id == pid,
        )
        .first()
    )
    old_budget = float(envelope.budget_amount) if envelope else 0.0
    old_snapshot = {
        "name": db_group.lab_group_name,
        "wbs_code": db_group.wbs_code,
        "budget": old_budget,
    }

    db_group.lab_group_name = group.name
    db_group.wbs_code = group.wbs_code
    db_group.description = group.description

    if envelope:
        envelope.budget_amount = group.budget
    else:
        envelope = Budget(
            period_id=pid,
            lab_group_id=group_id,
            lab_id=None,
            category_id=None,
            budget_amount=group.budget,
            updated_at=func.now(),
        )
        db.add(envelope)

    if hasattr(group, "assigned_lab_ids") and group.assigned_lab_ids:
        labs_to_update = (
            db.query(Lab).filter(Lab.lab_id.in_(group.assigned_lab_ids)).all()
        )
        for lab in labs_to_update:
            lab.lab_group_id = group_id

        budgets_to_update = (
            db.query(Budget).filter(Budget.lab_id.in_(group.assigned_lab_ids)).all()
        )
        for b in budgets_to_update:
            b.lab_group_id = group_id

    db.commit()

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="UPDATE",
        entity_name="LabGroup",
        record_id=str(group_id),
        old_value=old_snapshot,
        new_value={
            "name": db_group.lab_group_name,
            "wbs_code": db_group.wbs_code,
            "budget": requested_group_budget,
        },
        request=request,
    )

    background_tasks.add_task(check_and_notify_lab_group_thresholds, group_id)

    allocated = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == group_id,
            Budget.lab_id.isnot(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    return {
        "id": db_group.lab_group_id,
        "name": db_group.lab_group_name,
        "wbs_code": db_group.wbs_code,
        "description": db_group.description,
        "budget": requested_group_budget,
        "allocated_to_labs": allocated,
        "unallocated": requested_group_budget - allocated,
        "spent": total_spent,
        "threshold": 80,
    }


@router.delete("/labgroups/{group_id}")
def delete_lab_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Lab Group not found")

    old_snapshot = {
        "name": group.lab_group_name,
        "wbs_code": group.wbs_code,
    }

    try:
        budgets = db.query(Budget).filter(Budget.lab_group_id == group_id).all()
        for b in budgets:
            db.delete(b)

        labs = db.query(Lab).filter(Lab.lab_group_id == group_id).all()
        for lab in labs:
            lab.lab_group_id = None

        db.delete(group)
        db.commit()

        log_audit_action(
            db=db,
            user_id=current_user.user_id,
            action_type="DELETE",
            entity_name="LabGroup",
            record_id=str(group_id),
            old_value=old_snapshot,
            request=request,
        )

        return {
            "success": True,
            "message": "Lab group deleted and all associated labs unassigned.",
        }
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete this group because it is already tied to existing Purchase Requests or users.",
        )


# ==============================
# CATEGORIES API
# ==============================
@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(SpendingCategory).all()
    return [
        {
            "id": c.category_id,
            "name": c.category_name,
            "description": c.description or "",
        }
        for c in cats
    ]


@router.post("/categories", response_model=CategoryOut)
def create_category(
    cat_in: CategoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    existing_cat = (
        db.query(SpendingCategory)
        .filter(func.lower(SpendingCategory.category_name) == cat_in.name.lower())
        .first()
    )
    if existing_cat:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create category: The name '{cat_in.name}' is already in use.",
        )

    new_cat = SpendingCategory(
        category_name=cat_in.name, description=cat_in.description
    )
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="CREATE",
        entity_name="SpendingCategory",
        record_id=str(new_cat.category_id),
        new_value={"name": new_cat.category_name, "description": new_cat.description},
        request=request,
    )

    return {
        "id": new_cat.category_id,
        "name": new_cat.category_name,
        "description": new_cat.description or "",
    }


@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(
    cat_id: int,
    cat_in: CategoryCreate,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_cat = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == cat_id)
        .first()
    )
    if not db_cat:
        raise HTTPException(status_code=404)

    existing_cat = (
        db.query(SpendingCategory)
        .filter(
            func.lower(SpendingCategory.category_name) == cat_in.name.lower(),
            SpendingCategory.category_id != cat_id,
        )
        .first()
    )
    if existing_cat:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update category: The name '{cat_in.name}' is already in use.",
        )

    old_snapshot = {
        "name": db_cat.category_name,
        "description": db_cat.description,
    }

    db_cat.category_name = cat_in.name
    db_cat.description = cat_in.description
    db.commit()

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="UPDATE",
        entity_name="SpendingCategory",
        record_id=str(cat_id),
        old_value=old_snapshot,
        new_value={"name": db_cat.category_name, "description": db_cat.description},
        request=request,
    )

    return {
        "id": db_cat.category_id,
        "name": db_cat.category_name,
        "description": db_cat.description or "",
    }


@router.delete("/categories/{cat_id}")
def delete_category(
    cat_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    cat = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == cat_id)
        .first()
    )
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")

    old_snapshot = {"name": cat.category_name, "description": cat.description}

    try:
        db.delete(cat)
        db.commit()

        log_audit_action(
            db=db,
            user_id=current_user.user_id,
            action_type="DELETE",
            entity_name="SpendingCategory",
            record_id=str(cat_id),
            old_value=old_snapshot,
            request=request,
        )

        return {"success": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail=f"Cannot delete '{cat.category_name}' because it is in use by existing budgets or requests.",
        )


# ==============================
# LABS API
# ==============================
@router.get("/labs/orphaned")
def get_orphaned_labs(db: Session = Depends(get_db)):
    orphaned_labs = db.query(Lab).filter(Lab.lab_group_id.is_(None)).all()
    return [
        {"lab_id": lab.lab_id, "lab_name": lab.lab_name, "lab_code": lab.lab_code or ""}
        for lab in orphaned_labs
    ]


@router.get("/labs", response_model=List[LabOut])
def get_labs(
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    query = db.query(Lab)
    role_name = (
        (current_user.role.role_name if current_user.role else "").lower().strip()
    )

    if role_name == "teamlead":
        if not current_user.lab_group_id:
            return []
        query = query.filter(Lab.lab_group_id == current_user.lab_group_id)
    elif role_name == "labic":
        user_lab_ids = [a.lab_id for a in current_user.lab_assignments]
        if not user_lab_ids:
            return []
        query = query.filter(Lab.lab_id.in_(user_lab_ids))
    elif role_name != "admin":
        return []

    labs = query.all()
    result = []
    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()

    for lab in labs:
        budgets = (
            db.query(Budget)
            .filter(Budget.lab_id == lab.lab_id, Budget.period_id == pid)
            .all()
        )
        total_budget = sum(float(b.budget_amount) for b in budgets) if budgets else 0.0
        budget_map = {str(b.category_id): float(b.budget_amount) for b in budgets}

        primary_ic_assignment = (
            db.query(LabIcAssignment)
            .filter(
                LabIcAssignment.lab_id == lab.lab_id,
                LabIcAssignment.is_primary.is_(True),
            )
            .first()
        )
        if primary_ic_assignment and primary_ic_assignment.user:
            ic_name = primary_ic_assignment.user.full_name
            ic_email = primary_ic_assignment.user.email
        else:
            ic_name = ""
            ic_email = ""

        if active_period:
            total_spent = float(
                db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(
                    PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id
                )
                .filter(
                    PurchaseRequestLine.lab_id == lab.lab_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    _active_pr_status_filter(),
                )
                .scalar()
                or 0
            )

            spent_data = (
                db.query(
                    PurchaseRequestLine.category_id,
                    func.sum(PurchaseRequestLine.amount_gst),
                )
                .join(
                    PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id
                )
                .filter(
                    PurchaseRequestLine.lab_id == lab.lab_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    _active_pr_status_filter(),
                )
                .group_by(PurchaseRequestLine.category_id)
                .all()
            )
            spent_by_cat = {
                str(cat_id): float(amount)
                for cat_id, amount in spent_data
                if cat_id is not None
            }
        else:
            total_spent = 0.0
            spent_by_cat = {}

        result.append(
            {
                "id": lab.lab_id,
                "code": lab.lab_code or "",
                "name": lab.lab_name,
                "group": lab.group.lab_group_name if lab.group else "Unassigned",
                "group_id": lab.lab_group_id if lab.lab_group_id else 0,
                "venue": lab.venue or "",
                "budget": total_budget,
                "spent": total_spent,
                "ic_name": ic_name,
                "ic_email": ic_email,
                "budgets": budget_map,
                "spent_by_category": spent_by_cat,
            }
        )
    return result


@router.post("/labs", response_model=LabOut)
def create_lab(
    lab_in: LabCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    existing_lab = (
        db.query(Lab)
        .filter(func.lower(Lab.lab_code) == lab_in.lab_code.lower())
        .first()
    )
    if existing_lab:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot create lab: The code '{lab_in.lab_code}' is already in use by another lab.",
        )

    requested_total = sum(amount for amount in lab_in.budgets.values() if amount > 0)

    group_envelope = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == lab_in.lab_group_id,
            Budget.lab_id.is_(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    existing_allocated = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == lab_in.lab_group_id,
            Budget.lab_id.isnot(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    if (existing_allocated + requested_total) > group_envelope:
        remaining = group_envelope - existing_allocated
        raise HTTPException(
            status_code=400,
            detail=f"Budget Exceeded: You requested ${requested_total:,.2f}, but the Lab Group only has ${remaining:,.2f} of unallocated funds remaining.",
        )

    new_lab = Lab(
        lab_code=lab_in.lab_code,
        lab_name=lab_in.lab_name,
        lab_group_id=lab_in.lab_group_id,
        venue=lab_in.venue,
    )
    db.add(new_lab)
    db.flush()

    total_assigned = 0.0
    for cat_id_str, amount in lab_in.budgets.items():
        if amount > 0:
            b = Budget(
                period_id=pid,
                lab_group_id=new_lab.lab_group_id,
                lab_id=new_lab.lab_id,
                category_id=int(cat_id_str),
                budget_amount=amount,
                updated_at=func.now(),
            )
            db.add(b)
            total_assigned += amount

    db.commit()
    db.refresh(new_lab)

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="CREATE",
        entity_name="Lab",
        record_id=str(new_lab.lab_id),
        new_value={
            "code": new_lab.lab_code,
            "name": new_lab.lab_name,
            "venue": new_lab.venue,
            "budgets": lab_in.budgets,
        },
        request=request,
    )

    background_tasks.add_task(check_and_notify_lab_thresholds, new_lab.lab_id)
    if new_lab.lab_group_id:
        background_tasks.add_task(
            check_and_notify_lab_group_thresholds, new_lab.lab_group_id
        )

    return {
        "id": new_lab.lab_id,
        "code": new_lab.lab_code or "",
        "name": new_lab.lab_name,
        "group": new_lab.group.lab_group_name if new_lab.group else "Unassigned",
        "group_id": new_lab.lab_group_id,
        "venue": new_lab.venue,
        "budget": total_assigned,
        "spent": 0.0,
        "ic_name": lab_in.ic_name,
        "ic_email": lab_in.ic_email,
        "budgets": lab_in.budgets,
        "spent_by_category": {},
    }


@router.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(
    lab_id: int,
    lab_in: LabCreate,
    background_tasks: BackgroundTasks,
    request: Request,
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    db_lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404)

    pid = period_id if period_id is not None else get_or_create_current_period(db)

    existing_lab = (
        db.query(Lab)
        .filter(
            func.lower(Lab.lab_code) == lab_in.lab_code.lower(), Lab.lab_id != lab_id
        )
        .first()
    )

    if existing_lab:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot update lab: The code '{lab_in.lab_code}' is already in use by another lab.",
        )

    requested_total = sum(
        float(amount) for amount in lab_in.budgets.values() if amount and amount > 0
    )

    group_envelope = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == lab_in.lab_group_id,
            Budget.lab_id.is_(None),
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    existing_allocated = float(
        db.query(func.sum(Budget.budget_amount))
        .filter(
            Budget.lab_group_id == lab_in.lab_group_id,
            Budget.lab_id.isnot(None),
            Budget.lab_id != lab_id,
            Budget.period_id == pid,
        )
        .scalar()
        or 0
    )

    if (existing_allocated + requested_total) > group_envelope + 1e-6:
        remaining = group_envelope - existing_allocated
        raise HTTPException(
            status_code=400,
            detail=f"Budget Exceeded: You requested ${requested_total:,.2f}, but the Lab Group only has ${remaining:,.2f} of unallocated funds remaining.",
        )

    old_budgets_rows = (
        db.query(Budget).filter(Budget.lab_id == lab_id, Budget.period_id == pid).all()
    )
    old_budgets_map = {
        str(b.category_id): float(b.budget_amount) for b in old_budgets_rows
    }

    # Calculate current FY spend per category BEFORE mutating budgets
    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()
    if active_period:
        total_spent = float(
            db.query(func.sum(PurchaseRequestLine.amount_gst))
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .filter(
                PurchaseRequestLine.lab_id == lab_id,
                PurchaseRequest.request_date >= active_period.start_date,
                PurchaseRequest.request_date <= active_period.end_date,
                _active_pr_status_filter(),
            )
            .scalar()
            or 0
        )

        spent_data = (
            db.query(
                PurchaseRequestLine.category_id,
                func.sum(PurchaseRequestLine.amount_gst),
            )
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .filter(
                PurchaseRequestLine.lab_id == lab_id,
                PurchaseRequest.request_date >= active_period.start_date,
                PurchaseRequest.request_date <= active_period.end_date,
                _active_pr_status_filter(),
            )
            .group_by(PurchaseRequestLine.category_id)
            .all()
        )
        spent_by_cat = {
            str(cat_id): float(amount)
            for cat_id, amount in spent_data
            if cat_id is not None
        }
    else:
        total_spent = 0.0
        spent_by_cat = {}

    category_names = {
        str(c.category_id): c.category_name for c in db.query(SpendingCategory).all()
    }

    # Guard: Prevent shifting/reducing category budget below already-spent amount
    for cat_id_str, cat_spent in spent_by_cat.items():
        if cat_spent <= 0:
            continue
        old_cat_budget = float(old_budgets_map.get(cat_id_str, 0.0))
        new_cat_budget = float(lab_in.budgets.get(cat_id_str, 0.0))
        # If category was not in overrun, floor is cat_spent; if already in overrun, floor is old_cat_budget
        min_required_cat_budget = (
            cat_spent if old_cat_budget >= cat_spent else old_cat_budget
        )
        if new_cat_budget + 1e-6 < min_required_cat_budget:
            cat_name = category_names.get(cat_id_str, f"Category {cat_id_str}")
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Cannot reduce '{cat_name}' budget to ${new_cat_budget:,.2f}: "
                    f"${cat_spent:,.2f} has already been spent/utilised in this category."
                ),
            )

    old_total_lab_budget = sum(old_budgets_map.values())
    min_required_lab_budget = (
        total_spent if old_total_lab_budget >= total_spent else old_total_lab_budget
    )
    if requested_total + 1e-6 < min_required_lab_budget:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Cannot reduce Lab total budget to ${requested_total:,.2f}: "
                f"${total_spent:,.2f} has already been spent/utilised by this lab."
            ),
        )

    old_group_id = db_lab.lab_group_id
    old_snapshot = {
        "code": db_lab.lab_code,
        "name": db_lab.lab_name,
        "venue": db_lab.venue,
        "budgets": old_budgets_map,
    }

    db_lab.lab_code = lab_in.lab_code
    db_lab.lab_name = lab_in.lab_name
    db_lab.lab_group_id = lab_in.lab_group_id
    db_lab.venue = lab_in.venue

    db.query(Budget).filter(Budget.lab_id == lab_id, Budget.period_id == pid).delete()

    total_assigned = 0.0
    for cat_id_str, amount in lab_in.budgets.items():
        if amount > 0:
            b = Budget(
                period_id=pid,
                lab_group_id=db_lab.lab_group_id,
                lab_id=db_lab.lab_id,
                category_id=int(cat_id_str),
                budget_amount=amount,
                updated_at=func.now(),
            )
            db.add(b)
            total_assigned += amount

    db.commit()
    db.refresh(db_lab)

    log_audit_action(
        db=db,
        user_id=current_user.user_id,
        action_type="UPDATE",
        entity_name="Lab",
        record_id=str(db_lab.lab_id),
        old_value=old_snapshot,
        new_value={
            "code": db_lab.lab_code,
            "name": db_lab.lab_name,
            "venue": db_lab.venue,
            "budgets": lab_in.budgets,
        },
        request=request,
    )

    background_tasks.add_task(check_and_notify_lab_thresholds, db_lab.lab_id)
    if db_lab.lab_group_id:
        background_tasks.add_task(
            check_and_notify_lab_group_thresholds, db_lab.lab_group_id
        )
    if old_group_id and old_group_id != db_lab.lab_group_id:
        background_tasks.add_task(check_and_notify_lab_group_thresholds, old_group_id)

    return {
        "id": db_lab.lab_id,
        "code": db_lab.lab_code or "",
        "name": db_lab.lab_name,
        "group": db_lab.group.lab_group_name if db_lab.group else "Unassigned",
        "group_id": db_lab.lab_group_id,
        "venue": db_lab.venue,
        "budget": total_assigned,
        "spent": total_spent,
        "ic_name": lab_in.ic_name,
        "ic_email": lab_in.ic_email,
        "budgets": lab_in.budgets,
        "spent_by_category": spent_by_cat,
    }


@router.delete("/labs/{lab_id}")
def delete_lab(
    lab_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    old_snapshot = {
        "code": lab.lab_code,
        "name": lab.lab_name,
        "venue": lab.venue,
    }

    try:
        db.query(Budget).filter(Budget.lab_id == lab_id).delete()
        db.delete(lab)
        db.commit()

        log_audit_action(
            db=db,
            user_id=current_user.user_id,
            action_type="DELETE",
            entity_name="Lab",
            record_id=str(lab_id),
            old_value=old_snapshot,
            request=request,
        )

        return {"success": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400,
            detail="Cannot delete this lab because it is already tied to existing Purchase Requests or users.",
        )
