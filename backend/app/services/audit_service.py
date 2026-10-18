import ipaddress
import logging
from typing import Any, Optional
from fastapi import Request
from sqlalchemy.orm import Session
from app.models.staging import AuditLog

logger = logging.getLogger(__name__)


def _extract_valid_ip(request: Optional[Request]) -> Optional[str]:
    if not request:
        return None
    forwarded = request.headers.get("X-Forwarded-For")
    raw_ip = (
        forwarded.split(",")[0].strip()
        if forwarded
        else (request.client.host if request.client else None)
    )
    if not raw_ip:
        return None
    try:
        ipaddress.ip_address(raw_ip)
        return raw_ip
    except ValueError:
        return None


def log_audit_action(
    db: Session,
    user_id: int,
    action_type: str,
    entity_name: str,
    record_id: str,
    old_value: Optional[dict[str, Any]] = None,
    new_value: Optional[dict[str, Any]] = None,
    request: Optional[Request] = None,
) -> None:
    try:
        log_entry = AuditLog(
            user_id=user_id,
            action_type=action_type,
            entity_name=entity_name,
            record_id=str(record_id),
            old_value=old_value,
            new_value=new_value,
            ip_address=_extract_valid_ip(request),
        )
        db.add(log_entry)
        db.commit()
    except Exception as e:
        logger.error(f"Failed to write audit log: {e}")
        db.rollback()