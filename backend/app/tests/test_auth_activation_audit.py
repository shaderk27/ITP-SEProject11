from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.auth import Role, User
from app.models.staging import AuditLog
from app.repositories.auth_repository import AuthRepository
from app.services.auth_service import AuthService


def _user(active: bool):
    return SimpleNamespace(
        user_id=7,
        full_name="Test User",
        email="user@test.com",
        is_active=active,
        lab_group_id=None,
        lab_assignments=[],
    )


def test_deactivate_uses_repository_audit_transaction():
    repository = MagicMock()
    repository.get_user_by_id.return_value = _user(True)
    repository.set_user_activation_status.return_value = _user(False)
    service = AuthService(repository, MagicMock())

    result = service.deactivate_user(7, current_admin_id=3)

    repository.set_user_activation_status.assert_called_once_with(
        service.db, 7, False, acting_admin_id=3
    )
    assert result["is_active"] is False


def test_activate_uses_repository_audit_transaction():
    repository = MagicMock()
    repository.get_user_by_id.return_value = _user(False)
    repository.set_user_activation_status.return_value = _user(True)
    service = AuthService(repository, MagicMock())

    result = service.activate_user(7, current_admin_id=3)

    repository.set_user_activation_status.assert_called_once_with(
        service.db, 7, True, acting_admin_id=3
    )
    assert result["is_active"] is True


def test_activation_lifecycle_persists_admin_and_old_new_values(db, admin_user):
    labic_role = db.query(Role).filter(Role.role_name == "labic").one()
    target = User(
        role_id=labic_role.role_id,
        full_name="Activation Audit Test",
        email="activation.audit@test.com",
        staff_id="AUDIT-ACTIVATION",
        password_hash="placeholder_no_auth_yet",
        is_active=True,
    )
    db.add(target)
    db.flush()

    repository = AuthRepository()
    repository.set_user_activation_status(
        db,
        target.user_id,
        False,
        acting_admin_id=admin_user.user_id,
    )
    repository.set_user_activation_status(
        db,
        target.user_id,
        True,
        acting_admin_id=admin_user.user_id,
    )

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.entity_name == "users")
        .filter(AuditLog.record_id == str(target.user_id))
        .order_by(AuditLog.audit_id)
        .all()
    )

    assert [row.action_type for row in rows] == [
        "user_deactivated",
        "user_reactivated",
    ]
    assert all(row.user_id == admin_user.user_id for row in rows)
    assert all(row.created_at is not None for row in rows)
    assert rows[0].old_value == {"is_active": True}
    assert rows[0].new_value == {"is_active": False}
    assert rows[1].old_value == {"is_active": False}
    assert rows[1].new_value == {"is_active": True}
