from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
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
)
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User

from app.services.threshold_service import check_and_notify_lab_thresholds, check_and_notify_lab_group_thresholds
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
def create_period(payload: PeriodCreate, db: Session = Depends(get_db)):
    year = payload.year
    if year < 2000 or year > 2100:
        raise HTTPException(status_code=400, detail="Year must be between 2000 and 2100.")
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
    role_name = ((current_user.role.role_name if current_user.role else "").lower().strip())
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    query = db.query(LabGroup)
    if role_name == "teamlead":
        if not current_user.lab_group_id:
            return []
        query = query.filter(LabGroup.lab_group_id == current_user.lab_group_id)
    elif role_name == "labic":
        if not current_user.lab_id:
            return []
        user_lab = db.query(Lab).filter(Lab.lab_id == current_user.lab_id).first()
        if not user_lab or not user_lab.lab_group_id:
            return []
        query = query.filter(LabGroup.lab_group_id == user_lab.lab_group_id)
    elif role_name != "admin":
        return []

    groups = query.all()
    result = []
    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()

    for g in groups:
        total_budget_envelope = float(db.query(func.sum(Budget.budget_amount)).filter(
            Budget.lab_group_id == g.lab_group_id,
            Budget.lab_id.is_(None),
            Budget.period_id == pid
        ).scalar() or 0)

        allocated_to_labs = float(db.query(func.sum(Budget.budget_amount)).filter(
            Budget.lab_group_id == g.lab_group_id,
            Budget.lab_id.isnot(None),
            Budget.period_id == pid
        ).scalar() or 0)

        if active_period:
            total_spent = float(db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
                .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
                .filter(
                    Lab.lab_group_id == g.lab_group_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    or_(
                        PurchaseRequestLine.pr_status.is_(None),
                        and_(
                            PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                            PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                        ),
                    ),
                ).scalar() or 0)
        else:
            total_spent = 0.0

        result.append({
            "id": g.lab_group_id,
            "name": g.lab_group_name,
            "wbs_code": g.wbs_code or "",
            "description": g.description or "",
            "budget": total_budget_envelope,
            "allocated_to_labs": allocated_to_labs,
            "unallocated": total_budget_envelope - allocated_to_labs,
            "spent": total_spent,
            "threshold": 80,
        })
    return result


@router.post("/labgroups", response_model=LabGroupOut)
def create_lab_group(
    group: LabGroupCreate, 
    period_id: int | None = None,
    db: Session = Depends(get_db)
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)
    
    # --- PREVENT DUPLICATE WBS CODES ---
    existing_wbs = db.query(LabGroup).filter(func.lower(LabGroup.wbs_code) == group.wbs_code.lower()).first()
    if existing_wbs:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot create Lab Group: The WBS Prefix '{group.wbs_code}' is already in use by another group."
        )
    # -----------------------------------

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
            updated_at=func.now()
        )
        db.add(envelope)

    if hasattr(group, "assigned_lab_ids") and group.assigned_lab_ids:
        labs_to_update = db.query(Lab).filter(Lab.lab_id.in_(group.assigned_lab_ids)).all()
        for lab in labs_to_update:
            lab.lab_group_id = new_group.lab_group_id

        budgets_to_update = db.query(Budget).filter(Budget.lab_id.in_(group.assigned_lab_ids)).all()
        for b in budgets_to_update:
            b.lab_group_id = new_group.lab_group_id

    db.commit()
    db.refresh(new_group)
    
    return {
        "id": new_group.lab_group_id,
        "name": new_group.lab_group_name,
        "wbs_code": new_group.wbs_code,
        "description": new_group.description,
        "budget": float(group.budget),
        "allocated_to_labs": 0.0,
        "unallocated": float(group.budget),
        "spent": 0.0,
        "threshold": 80,
    }


@router.put("/labgroups/{group_id}", response_model=LabGroupOut)
def update_lab_group(
    group_id: int, 
    group: LabGroupCreate, 
    period_id: int | None = None,
    db: Session = Depends(get_db)
):
    db_group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404)

    pid = period_id if period_id is not None else get_or_create_current_period(db)

    # --- PREVENT DUPLICATE WBS CODES ON RENAME ---
    existing_wbs = db.query(LabGroup).filter(
        func.lower(LabGroup.wbs_code) == group.wbs_code.lower(),
        LabGroup.lab_group_id != group_id
    ).first()
    if existing_wbs:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot update Lab Group: The WBS Prefix '{group.wbs_code}' is already in use by another group."
        )
    # ---------------------------------------------

    db_group.lab_group_name = group.name
    db_group.wbs_code = group.wbs_code
    db_group.description = group.description

    envelope = db.query(Budget).filter(
        Budget.lab_group_id == group_id,
        Budget.lab_id.is_(None),
        Budget.period_id == pid
    ).first()

    if envelope:
        envelope.budget_amount = group.budget
    else:
        envelope = Budget(
            period_id=pid,
            lab_group_id=group_id,
            lab_id=None,
            category_id=None,
            budget_amount=group.budget,
            updated_at=func.now()
        )
        db.add(envelope)

    if hasattr(group, "assigned_lab_ids") and group.assigned_lab_ids:
        labs_to_update = db.query(Lab).filter(Lab.lab_id.in_(group.assigned_lab_ids)).all()
        for lab in labs_to_update:
            lab.lab_group_id = group_id

        budgets_to_update = db.query(Budget).filter(Budget.lab_id.in_(group.assigned_lab_ids)).all()
        for b in budgets_to_update:
            b.lab_group_id = group_id

    db.commit()

    allocated = float(db.query(func.sum(Budget.budget_amount)).filter(
        Budget.lab_group_id == group_id,
        Budget.lab_id.isnot(None),
        Budget.period_id == pid
    ).scalar() or 0)

    return {
        "id": db_group.lab_group_id,
        "name": db_group.lab_group_name,
        "wbs_code": db_group.wbs_code,
        "description": db_group.description,
        "budget": float(group.budget),
        "allocated_to_labs": allocated,
        "unallocated": float(group.budget) - allocated,
        "spent": 0.0,
        "threshold": 80,
    }


@router.delete("/labgroups/{group_id}")
def delete_lab_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Lab Group not found")

    try:
        budgets = db.query(Budget).filter(Budget.lab_group_id == group_id).all()
        for b in budgets:
            db.delete(b) 

        labs = db.query(Lab).filter(Lab.lab_group_id == group_id).all()
        for lab in labs:
            lab.lab_group_id = None

        db.delete(group)
        db.commit()
        return {"success": True, "message": "Lab group deleted and all associated labs unassigned."}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete this group because it is already tied to existing Purchase Requests or users."
        )


# ==============================
# CATEGORIES API
# ==============================
@router.get("/categories", response_model=List[CategoryOut])
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(SpendingCategory).all()
    return [
        {"id": c.category_id, "name": c.category_name, "description": c.description or ""}
        for c in cats
    ]

@router.post("/categories", response_model=CategoryOut)
def create_category(cat_in: CategoryCreate, db: Session = Depends(get_db)):
    # --- PREVENT DUPLICATE CATEGORY NAMES ---
    existing_cat = db.query(SpendingCategory).filter(func.lower(SpendingCategory.category_name) == cat_in.name.lower()).first()
    if existing_cat:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot create category: The name '{cat_in.name}' is already in use."
        )
    # ----------------------------------------
    
    new_cat = SpendingCategory(category_name=cat_in.name, description=cat_in.description)
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return {"id": new_cat.category_id, "name": new_cat.category_name, "description": new_cat.description or ""}

@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: int, cat_in: CategoryCreate, db: Session = Depends(get_db)):
    db_cat = db.query(SpendingCategory).filter(SpendingCategory.category_id == cat_id).first()
    if not db_cat:
        raise HTTPException(status_code=404)

    # --- PREVENT DUPLICATE CATEGORY NAMES ON RENAME ---
    existing_cat = db.query(SpendingCategory).filter(
        func.lower(SpendingCategory.category_name) == cat_in.name.lower(),
        SpendingCategory.category_id != cat_id
    ).first()
    if existing_cat:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot update category: The name '{cat_in.name}' is already in use."
        )
    # --------------------------------------------------

    db_cat.category_name = cat_in.name
    db_cat.description = cat_in.description
    db.commit()
    return {"id": db_cat.category_id, "name": db_cat.category_name, "description": db_cat.description or ""}

@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = db.query(SpendingCategory).filter(SpendingCategory.category_id == cat_id).first()
    if not cat:
        raise HTTPException(status_code=404, detail="Category not found.")
    try:
        db.delete(cat)
        db.commit()
        return {"success": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail=f"Cannot delete '{cat.category_name}' because it is in use by existing budgets or requests.")


# ==============================
# LABS API
# ==============================
@router.get("/labs/orphaned")
def get_orphaned_labs(db: Session = Depends(get_db)):
    orphaned_labs = db.query(Lab).filter(Lab.lab_group_id.is_(None)).all()
    return [{"lab_id": lab.lab_id, "lab_name": lab.lab_name, "lab_code": lab.lab_code or ""} for lab in orphaned_labs]


@router.get("/labs", response_model=List[LabOut])
def get_labs(
    period_id: int | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)
    
    query = db.query(Lab)
    role_name = ((current_user.role.role_name if current_user.role else "").lower().strip())
    
    if role_name == "teamlead":
        if not current_user.lab_group_id: return []
        query = query.filter(Lab.lab_group_id == current_user.lab_group_id)
    elif role_name == "labic":
        if not current_user.lab_id: return []
        query = query.filter(Lab.lab_id == current_user.lab_id)
    elif role_name != "admin":
        return []
        
    labs = query.all()
    result = []
    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()

    for lab in labs:
        budgets = db.query(Budget).filter(Budget.lab_id == lab.lab_id, Budget.period_id == pid).all()
        total_budget = sum(float(b.budget_amount) for b in budgets) if budgets else 0.0
        budget_map = {str(b.category_id): float(b.budget_amount) for b in budgets}

        if active_period:
            total_spent = float(db.query(func.sum(PurchaseRequestLine.amount_gst))
                .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
                .filter(
                    PurchaseRequestLine.lab_id == lab.lab_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    or_(
                        PurchaseRequestLine.pr_status.is_(None),
                        and_(
                            PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                            PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                        ),
                    ),
                ).scalar() or 0)

            spent_data = (
                db.query(PurchaseRequestLine.category_id, func.sum(PurchaseRequestLine.amount_gst))
                .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
                .filter(
                    PurchaseRequestLine.lab_id == lab.lab_id,
                    PurchaseRequest.request_date >= active_period.start_date,
                    PurchaseRequest.request_date <= active_period.end_date,
                    or_(
                        PurchaseRequestLine.pr_status.is_(None),
                        and_(
                            PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                            PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                        ),
                    ),
                ).group_by(PurchaseRequestLine.category_id).all()
            )
            spent_by_cat = {str(cat_id): float(amount) for cat_id, amount in spent_data if cat_id is not None}
        else:
            total_spent = 0.0
            spent_by_cat = {}

        result.append({
            "id": lab.lab_id,
            "code": lab.lab_code or "",
            "name": lab.lab_name,
            "group": lab.group.lab_group_name if lab.group else "Unassigned",
            "group_id": lab.lab_group_id if lab.lab_group_id else 0,
            "venue": lab.venue or "",
            "budget": total_budget,
            "spent": total_spent,
            "ic_name": "",
            "ic_email": "",
            "budgets": budget_map,
            "spent_by_category": spent_by_cat,
        })
    return result


@router.post("/labs", response_model=LabOut)
def create_lab(
    lab_in: LabCreate,
    period_id: int | None = None,
    db: Session = Depends(get_db),
):
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    # --- PREVENT DUPLICATE LAB CODES ---
    existing_lab = db.query(Lab).filter(func.lower(Lab.lab_code) == lab_in.lab_code.lower()).first()
    if existing_lab:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot create lab: The code '{lab_in.lab_code}' is already in use by another lab."
        )

    # --- TOP DOWN BUDGET VALIDATION ---
    requested_total = sum(amount for amount in lab_in.budgets.values() if amount > 0)
    
    group_envelope = float(db.query(func.sum(Budget.budget_amount)).filter(
        Budget.lab_group_id == lab_in.lab_group_id,
        Budget.lab_id.is_(None),
        Budget.period_id == pid
    ).scalar() or 0)

    existing_allocated = float(db.query(func.sum(Budget.budget_amount)).filter(
        Budget.lab_group_id == lab_in.lab_group_id,
        Budget.lab_id.isnot(None),
        Budget.period_id == pid
    ).scalar() or 0)

    if (existing_allocated + requested_total) > group_envelope:
        remaining = group_envelope - existing_allocated
        raise HTTPException(
            status_code=400, 
            detail=f"Budget Exceeded: You requested ${requested_total:,.2f}, but the Lab Group only has ${remaining:,.2f} of unallocated funds remaining."
        )
    # ----------------------------------

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
    }


@router.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(
    lab_id: int,
    lab_in: LabCreate,
    background_tasks: BackgroundTasks,
    period_id: int | None = None,
    db: Session = Depends(get_db),
):
    db_lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404)
        
    pid = period_id if period_id is not None else get_or_create_current_period(db)

    # --- PREVENT DUPLICATE LAB CODES ---
    existing_lab = db.query(Lab).filter(
        func.lower(Lab.lab_code) == lab_in.lab_code.lower(),
        Lab.lab_id != lab_id 
    ).first()
    
    if existing_lab:
        raise HTTPException(
            status_code=400, 
            detail=f"Cannot update lab: The code '{lab_in.lab_code}' is already in use by another lab."
        )

    # --- TOP DOWN BUDGET VALIDATION ---
    requested_total = sum(amount for amount in lab_in.budgets.values() if amount > 0)
    
    group_envelope = float(db.query(func.sum(Budget.budget_amount)).filter(
        Budget.lab_group_id == lab_in.lab_group_id,
        Budget.lab_id.is_(None),
        Budget.period_id == pid
    ).scalar() or 0)

    existing_allocated = float(db.query(func.sum(Budget.budget_amount)).filter(
        Budget.lab_group_id == lab_in.lab_group_id,
        Budget.lab_id.isnot(None),
        Budget.lab_id != lab_id, 
        Budget.period_id == pid
    ).scalar() or 0)

    if (existing_allocated + requested_total) > group_envelope:
        remaining = group_envelope - existing_allocated
        raise HTTPException(
            status_code=400, 
            detail=f"Budget Exceeded: You requested ${requested_total:,.2f}, but the Lab Group only has ${remaining:,.2f} of unallocated funds remaining."
        )
    # ----------------------------------

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

    background_tasks.add_task(check_and_notify_lab_thresholds, db_lab.lab_id)
    background_tasks.add_task(check_and_notify_lab_group_thresholds, db_lab.lab_group_id)

    active_period = db.query(BudgetPeriod).filter(BudgetPeriod.period_id == pid).first()
    if active_period:
        total_spent = float(db.query(func.sum(PurchaseRequestLine.amount_gst))
            .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
            .filter(
                PurchaseRequestLine.lab_id == db_lab.lab_id,
                PurchaseRequest.request_date >= active_period.start_date,
                PurchaseRequest.request_date <= active_period.end_date,
                or_(
                    PurchaseRequestLine.pr_status.is_(None),
                    and_(
                        PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                        PurchaseRequestLine.pr_status.not_ilike("%cancel%"),
                    ),
                ),
            ).scalar() or 0)
    else:
        total_spent = 0.0

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
    }


@router.delete("/labs/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db)):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    try:
        db.query(Budget).filter(Budget.lab_id == lab_id).delete()
        db.delete(lab)
        db.commit()
        return {"success": True}
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=400, 
            detail="Cannot delete this lab because it is already tied to existing Purchase Requests or users."
        )