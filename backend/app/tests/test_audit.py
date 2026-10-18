from datetime import datetime, timezone
from unittest.mock import MagicMock
from fastapi.testclient import TestClient

from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.services.audit_service import log_audit_action

client = TestClient(app)


def test_get_audit_logs_as_admin_succeeds():
    admin_user = User(
        user_id=1,
        email="admin@test.com",
        role_id=1,
        role=MagicMock(role_name="admin"),
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_log = MagicMock()
    mock_log.audit_id = 1
    mock_log.user_id = 1
    mock_log.action_type = "CREATE"
    mock_log.entity_name = "Lab"
    mock_log.record_id = "10"
    mock_log.old_value = None
    mock_log.new_value = {"code": "L1"}
    mock_log.ip_address = "127.0.0.1"
    mock_log.created_at = datetime.now(timezone.utc)

    mock_db.query.return_value.outerjoin.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (mock_log, "Admin User", "admin@test.com")
    ]

    response = client.get("/api/audit/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["entity_name"] == "Lab"

    app.dependency_overrides.clear()


def test_get_audit_logs_as_non_admin_throws_403():
    labic_user = User(
        user_id=2,
        email="labic@test.com",
        role_id=3,
        role=MagicMock(role_name="labic"),
    )
    app.dependency_overrides[get_current_user] = lambda: labic_user

    response = client.get("/api/audit/")
    assert response.status_code == 403

    app.dependency_overrides.clear()


def test_log_audit_action_service_inserts_correctly():
    mock_db = MagicMock()
    log_audit_action(
        db=mock_db,
        user_id=1,
        action_type="UPDATE",
        entity_name="LabGroup",
        record_id="5",
        old_value={"budget": 1000},
        new_value={"budget": 2000},
    )
    assert mock_db.add.called
    assert mock_db.commit.called