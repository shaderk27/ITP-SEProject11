from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List
from datetime import date

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
        start_date=date(start_year, 4, 1),
        end_date=date(start_year + 1, 3, 31),
    )
    db.add(new_period)
    db.commit()
    db.refresh(new_period)

    return new_period.period_id


# ==============================
# LAB GROUPS API
# ==============================
@router.get("/labgroups", response_model=List[LabGroupOut])
def get_lab_groups(db: Session = Depends(get_db)):
    groups = db.query(LabGroup).all()
    result = []
    for g in groups:
        total_budget = (
            db.query(func.sum(Budget.budget_amount))
            .filter(Budget.lab_group_id == g.lab_group_id)
            .scalar()
            or 0
        )
        result.append(
            {
                "id": g.lab_group_id,
                "name": g.lab_group_name,
                "wbs_code": g.wbs_code or "",
                "description": g.description or "",
                "budget": total_budget,
                "threshold": 80,
            }
        )
    return result


@router.post("/labgroups", response_model=LabGroupOut)
def create_lab_group(group: LabGroupCreate, db: Session = Depends(get_db)):
    new_group = LabGroup(
        lab_group_name=group.name,
        wbs_code=group.wbs_code,
        description=group.description,
    )
    db.add(new_group)
    db.flush()  # Flush to generate the new ID without committing yet

    # NEW: Bulk Claim Orphaned Labs & Sync Budgets Explicitly
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
    return {
        "id": new_group.lab_group_id,
        "name": new_group.lab_group_name,
        "wbs_code": new_group.wbs_code,
        "description": new_group.description,
        "budget": 0,
        "threshold": 80,
    }


@router.put("/labgroups/{group_id}", response_model=LabGroupOut)
def update_lab_group(
    group_id: int, group: LabGroupCreate, db: Session = Depends(get_db)
):
    db_group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not db_group:
        raise HTTPException(status_code=404)

    db_group.lab_group_name = group.name
    db_group.wbs_code = group.wbs_code
    db_group.description = group.description

    # NEW: Bulk Claim Orphaned Labs during Edit & Sync Budgets Explicitly
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
    return {
        "id": db_group.lab_group_id,
        "name": db_group.lab_group_name,
        "wbs_code": db_group.wbs_code,
        "description": db_group.description,
        "budget": 0,
        "threshold": 80,
    }


@router.delete("/labgroups/{group_id}")
def delete_lab_group(group_id: int, db: Session = Depends(get_db)):
    # 1. Unassign the group from all Budgets first explicitly
    budgets = db.query(Budget).filter(Budget.lab_group_id == group_id).all()
    for b in budgets:
        b.lab_group_id = None

    # 2. Unassign the group from all Labs explicitly
    labs = db.query(Lab).filter(Lab.lab_group_id == group_id).all()
    for lab in labs:
        lab.lab_group_id = None

    # 3. Safely delete the Lab Group
    group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Lab Group not found")

    db.delete(group)
    db.commit()

    return {
        "success": True,
        "message": "Lab group deleted and all associated labs and budgets unassigned.",
    }


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
def create_category(cat_in: CategoryCreate, db: Session = Depends(get_db)):
    new_cat = SpendingCategory(
        category_name=cat_in.name, description=cat_in.description
    )
    db.add(new_cat)
    db.commit()
    db.refresh(new_cat)
    return {
        "id": new_cat.category_id,
        "name": new_cat.category_name,
        "description": new_cat.description or "",
    }


@router.put("/categories/{cat_id}", response_model=CategoryOut)
def update_category(cat_id: int, cat_in: CategoryCreate, db: Session = Depends(get_db)):
    db_cat = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == cat_id)
        .first()
    )
    if not db_cat:
        raise HTTPException(status_code=404)
    db_cat.category_name = cat_in.name
    db_cat.description = cat_in.description
    db.commit()
    return {
        "id": db_cat.category_id,
        "name": db_cat.category_name,
        "description": db_cat.description or "",
    }


@router.delete("/categories/{cat_id}")
def delete_category(cat_id: int, db: Session = Depends(get_db)):
    cat = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_id == cat_id)
        .first()
    )
    if cat:
        db.delete(cat)
        db.commit()
    return {"success": True}


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
def get_labs(db: Session = Depends(get_db)):
    labs = db.query(Lab).all()
    result = []
    for lab in labs:
        budgets = db.query(Budget).filter(Budget.lab_id == lab.lab_id).all()
        total_budget = sum(b.budget_amount for b in budgets) if budgets else 0
        budget_map = {str(b.category_id): float(b.budget_amount) for b in budgets}
        result.append(
            {
                "id": lab.lab_id,
                "code": lab.lab_code or "",
                "name": lab.lab_name,
                "group": lab.group.lab_group_name if lab.group else "Unassigned",
                "group_id": lab.lab_group_id if lab.lab_group_id else 0,
                "venue": lab.venue or "",
                "budget": total_budget,
                "ic_name": "",
                "ic_email": "",
                "budgets": budget_map,
            }
        )
    return result


@router.post("/labs", response_model=LabOut)
def create_lab(lab_in: LabCreate, db: Session = Depends(get_db)):
    current_period_id = get_or_create_current_period(db)
    new_lab = Lab(
        lab_code=lab_in.lab_code,
        lab_name=lab_in.lab_name,
        lab_group_id=lab_in.lab_group_id,
        venue=lab_in.venue,
    )
    db.add(new_lab)
    db.flush()
    total_assigned = 0
    for cat_id_str, amount in lab_in.budgets.items():
        if amount > 0:
            b = Budget(
                period_id=current_period_id,
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
        "ic_name": lab_in.ic_name,
        "ic_email": lab_in.ic_email,
        "budgets": lab_in.budgets,
    }


@router.put("/labs/{lab_id}", response_model=LabOut)
def update_lab(lab_id: int, lab_in: LabCreate, db: Session = Depends(get_db)):
    db_lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not db_lab:
        raise HTTPException(status_code=404)
    current_period_id = get_or_create_current_period(db)
    db_lab.lab_code = lab_in.lab_code
    db_lab.lab_name = lab_in.lab_name
    db_lab.lab_group_id = lab_in.lab_group_id
    db_lab.venue = lab_in.venue
    db.query(Budget).filter(Budget.lab_id == lab_id).delete()
    total_assigned = 0
    for cat_id_str, amount in lab_in.budgets.items():
        if amount > 0:
            b = Budget(
                period_id=current_period_id,
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
    return {
        "id": db_lab.lab_id,
        "code": db_lab.lab_code or "",
        "name": db_lab.lab_name,
        "group": db_lab.group.lab_group_name if db_lab.group else "Unassigned",
        "group_id": db_lab.lab_group_id,
        "venue": db_lab.venue,
        "budget": total_assigned,
        "ic_name": lab_in.ic_name,
        "ic_email": lab_in.ic_email,
        "budgets": lab_in.budgets,
    }


@router.delete("/labs/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db)):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if lab:
        db.delete(lab)
        db.commit()
    return {"success": True}


@router.put("/labs/{lab_id}/unassign")
def unassign_lab_from_group(lab_id: int, db: Session = Depends(get_db)):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")

    # 1. Unassign Lab
    lab.lab_group_id = None

    # 2. Unassign Budgets explicitly
    budgets = db.query(Budget).filter(Budget.lab_id == lab_id).all()
    for b in budgets:
        b.lab_group_id = None

    db.commit()
    return {"success": True, "message": "Lab successfully removed from the group."}
