from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.staging import AuditLog

router = APIRouter(prefix="/api/audit", tags=["Audit"])


@router.get("/")
def get_audit_logs(
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    role_name = (
        (current_user.role.role_name if current_user.role else "").lower().strip()
    )
    if role_name != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Administrators can view system audit logs.",
        )

    rows = (
        db.query(AuditLog, User.full_name, User.email)
        .outerjoin(User, AuditLog.user_id == User.user_id)
        .order_by(AuditLog.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "audit_id": log.audit_id,
            "user_id": log.user_id,
            "user_name": full_name or email or "System",
            "user_email": email or "",
            "action_type": log.action_type,
            "entity_name": log.entity_name,
            "record_id": log.record_id,
            "old_value": log.old_value,
            "new_value": log.new_value,
            "ip_address": str(log.ip_address) if log.ip_address else None,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log, full_name, email in rows
    ]
