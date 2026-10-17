from fastapi.testclient import TestClient
from unittest.mock import MagicMock
from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.services.audit_service import log_audit_action
from datetime import datetime, timezone

client = TestClient(app)

def test_get_audit_logs_as_admin_succeeds():
    # 1. Setup Admin Mock
    admin_user = User(
        user_id=1, email="admin@test.com", role_id=1, role=MagicMock(role_name="admin")
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user

    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # 2. Mock the Audit Log Database Row
    mock_log = MagicMock()
    mock_log.audit_id = 1
    mock_log.action_type = "CREATE"
    mock_log.entity_name = "Lab"
    mock_log.record_id = "10"
    mock_log.old_value = None
    mock_log.new_value = {"code": "L1"}
    mock_log.ip_address = "127.0.0.1"
    mock_log.created_at = datetime.now(timezone.utc)

    # The API query expects a list of tuples: (AuditLog, user_name, user_email)
    mock_db.query.return_value.outerjoin.return_value.order_by.return_value.limit.return_value.all.return_value = [
        (mock_log, "Admin User", "admin@test.com")
    ]

    # 3. Execute
    response = client.get("/api/audit/")
    
    # 4. Assert
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["action_type"] == "CREATE"
    assert data[0]["user_name"] == "Admin User"
    assert data[0]["ip_address"] == "127.0.0.1"


def test_get_audit_logs_as_non_admin_throws_403():
    # 1. Setup Lab IC Mock
    labic_user = User(
        user_id=2, email="labic@test.com", role_id=3, role=MagicMock(role_name="labic")
    )
    app.dependency_overrides[get_current_user] = lambda: labic_user

    # 2. Execute
    response = client.get("/api/audit/")
    
    # 3. Assert Strict RBAC Block
    assert response.status_code == 403
    assert response.json()["detail"] == "Unauthorized. Admins only."


def test_log_audit_action_service_inserts_correctly():
    # 1. Setup Mock DB and Request
    mock_db = MagicMock()
    mock_request = MagicMock()
    mock_request.client.host = "192.168.1.50"

    # 2. Fire the Service
    log_audit_action(
        db=mock_db,
        user_id=99,
        action_type="UPDATE",
        entity_name="LabGroup",
        record_id="5",
        old_value={"budget": 100},
        new_value={"budget": 200},
        request=mock_request
    )

    # 3. Assert DB Commits
    assert mock_db.add.called is True
    assert mock_db.commit.called is True
    
    # 4. Inspect the exact object that was passed to db.add()
    added_obj = mock_db.add.call_args[0][0]
    assert added_obj.user_id == 99
    assert added_obj.action_type == "UPDATE"
    assert added_obj.entity_name == "LabGroup"
    assert added_obj.record_id == "5"
    assert added_obj.old_value == {"budget": 100}
    assert added_obj.new_value == {"budget": 200}
    assert added_obj.ip_address == "192.168.1.50"