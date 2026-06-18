from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.models.config import LabGroup, Lab, LabGroupOut, LabOut, LabGroupCreate, LabCreate
from app.database import get_db 

router = APIRouter(prefix="/api/config", tags=["Configuration"])

# --- LAB GROUPS API ---

@router.get("/labgroups", response_model=List[LabGroupOut])
def get_lab_groups(db: Session = Depends(get_db)):
    groups = db.query(LabGroup).all()
    return [{"id": g.lab_group_id, "name": g.lab_group_name, "budget": 0, "threshold": 80} for g in groups]

@router.post("/labgroups", response_model=LabGroupOut)
def create_lab_group(group: LabGroupCreate, db: Session = Depends(get_db)):
    new_group = LabGroup(
        lab_group_name=group.name,
        wbs_code=group.wbs_code,
        description=group.description
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    return {"id": new_group.lab_group_id, "name": new_group.lab_group_name, "budget": 0, "threshold": 80}

@router.delete("/labgroups/{group_id}")
def delete_lab_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Lab Group not found")
    db.delete(group)
    db.commit()
    return {"success": True}


# --- LABS API ---

@router.get("/labs", response_model=List[LabOut])
def get_labs(db: Session = Depends(get_db)):
    labs = db.query(Lab).all()
    return [{
        "id": l.lab_id,
        "code": l.lab_code or "N/A",
        "name": l.lab_name,
        "group": l.group.lab_group_name if l.group else "Unassigned",
        "budget": 0,
        "ic": "Pending Assignment" # Temporarily hardcoded until W7-01 users integration
    } for l in labs]

@router.post("/labs", response_model=LabOut)
def create_lab(lab_in: LabCreate, db: Session = Depends(get_db)):
    new_lab = Lab(
        lab_code=lab_in.lab_code,
        lab_name=lab_in.lab_name,
        lab_group_id=lab_in.lab_group_id,
        venue=lab_in.venue
    )
    db.add(new_lab)
    db.commit()
    db.refresh(new_lab)
    
    return {
        "id": new_lab.lab_id,
        "code": new_lab.lab_code or "N/A",
        "name": new_lab.lab_name,
        "group": new_lab.group.lab_group_name if new_lab.group else "Unassigned",
        "budget": 0,
        "ic": lab_in.ic_name or "Pending Assignment"
    }

@router.delete("/labs/{lab_id}")
def delete_lab(lab_id: int, db: Session = Depends(get_db)):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        raise HTTPException(status_code=404, detail="Lab not found")
    db.delete(lab)
    db.commit()
    return {"success": True}