from datetime import date, datetime, time, timedelta
from typing import Literal

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
    user_id: int | None = Query(None),
    action: str | None = Query(None, max_length=100),
    module: str | None = Query(None, max_length=100),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    sort: Literal["newest", "oldest"] = Query("newest"),
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

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="date_from must be on or before date_to.",
        )

    query = db.query(AuditLog, User.full_name, User.email).outerjoin(
        User, AuditLog.user_id == User.user_id
    )
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action and action.strip():
        query = query.filter(AuditLog.action_type.ilike(f"%{action.strip()}%"))
    if module and module.strip():
        query = query.filter(AuditLog.entity_name.ilike(f"%{module.strip()}%"))
    if date_from:
        query = query.filter(
            AuditLog.created_at >= datetime.combine(date_from, time.min)
        )
    if date_to:
        query = query.filter(
            AuditLog.created_at
            < datetime.combine(date_to + timedelta(days=1), time.min)
        )

    order = (
        AuditLog.created_at.asc() if sort == "oldest" else AuditLog.created_at.desc()
    )
    rows = query.order_by(order).limit(limit).all()

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
