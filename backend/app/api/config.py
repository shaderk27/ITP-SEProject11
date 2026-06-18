from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List

# Import the DB models and Pydantic schemas we made
from app.models.config import LabGroup, Lab, LabGroupOut, LabOut, LabGroupCreate
from fastapi import HTTPException
from app.database import get_db 

router = APIRouter(prefix="/api/config", tags=["Configuration"])

@router.get("/labgroups", response_model=List[LabGroupOut])
def get_lab_groups(db: Session = Depends(get_db)):
    # 1. Fetch the real rows from the PostgreSQL lab_groups table
    groups = db.query(LabGroup).all()
    
    # 2. Format them to match the Pydantic schema
    result = []
    for g in groups:
        result.append({
            "id": g.lab_group_id,
            "name": g.lab_group_name,
            "budget": 0,       # Placeholder: To be joined with the budgets table later
            "threshold": 80    # Placeholder: To be joined with alert_thresholds later
        })
    return result

@router.get("/labs", response_model=List[LabOut])
def get_labs(db: Session = Depends(get_db)):
    # 1. Fetch the real rows from the PostgreSQL labs table
    labs = db.query(Lab).all()
    
    # 2. Format them to match the Pydantic schema
    result = []
    for l in labs:
        result.append({
            "id": l.lab_id,
            "code": l.lab_code or "N/A",
            "name": l.lab_name,
            "group": l.group.lab_group_name if l.group else "Unassigned",
            "budget": 0,
            "ic": "Pending Assignment" # To be joined with the users table later
        })
    return result


#Create Lab Group
@router.post("/labgroups", response_model=LabGroupOut)
def create_lab_group(group: LabGroupCreate, db: Session = Depends(get_db)):
    # Create the new database row
    new_group = LabGroup(
        lab_group_name=group.name,
        wbs_code=group.wbs_code,
        description=group.description
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    
    # Return it to the frontend so the table updates instantly
    return {
        "id": new_group.lab_group_id,
        "name": new_group.lab_group_name,
        "budget": 0,
        "threshold": 80
    }

#Delete lab group
@router.delete("/labgroups/{group_id}")
def delete_lab_group(group_id: int, db: Session = Depends(get_db)):
    # Find the row and delete it
    group = db.query(LabGroup).filter(LabGroup.lab_group_id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Lab Group not found")
    
    db.delete(group)
    db.commit()
    return {"success": True}