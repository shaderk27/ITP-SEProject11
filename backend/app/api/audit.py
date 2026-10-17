from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.config import AuditLog # Adjust based on your models

router = APIRouter(prefix="/api/audit", tags=["Audit Logs"])

@router.get("/")
def get_audit_logs(
    limit: int = 100,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # STRICT ADMIN ENFORCEMENT
    if not current_user.role or current_user.role.role_name.lower() != "admin":
        raise HTTPException(status_code=403, detail="Unauthorized. Admins only.")

    logs = (
        db.query(AuditLog, User.full_name, User.email)
        .outerjoin(User, AuditLog.user_id == User.user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    result = []
    for log, user_name, user_email in logs:
        result.append({
            "audit_id": log.audit_id,
            "action_type": log.action_type,
            "entity_name": log.entity_name,
            "record_id": log.record_id,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "created_at": log.created_at.isoformat(),
            "user_name": user_name or "System/Unknown",
            "user_email": user_email or ""
        })

    return result