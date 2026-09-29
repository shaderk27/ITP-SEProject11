from sqlalchemy.orm import Session
from fastapi import Request
import json

def log_audit_action(
    db: Session,
    user_id: int,
    action_type: str,
    entity_name: str,
    record_id: str,
    old_value: dict | None = None,
    new_value: dict | None = None,
    request: Request | None = None
):
    from app.models.config import AuditLog # Adjust import based on your models

    ip_address = None
    if request and request.client:
        ip_address = request.client.host

    audit_entry = AuditLog(
        user_id=user_id,
        action_type=action_type,
        entity_name=entity_name,
        record_id=str(record_id),
        old_value=old_value,
        new_value=new_value,
        ip_address=ip_address
    )
    
    db.add(audit_entry)
    db.commit()