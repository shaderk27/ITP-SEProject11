from datetime import datetime, timezone
from unittest.mock import MagicMock
from fastapi.testclient import TestClient
from starlette.requests import Request

from app.main import app
from app.api.config import create_category, delete_category, update_category
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User
from app.models.config import CategoryCreate
from app.models.staging import AuditLog
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


def test_audit_rejects_reversed_date_filter():
    admin_user = User(
        user_id=1,
        email="admin@test.com",
        role_id=1,
        role=MagicMock(role_name="admin"),
    )
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_db] = lambda: MagicMock()

    response = client.get("/api/audit/?date_from=2026-10-20&date_to=2026-10-01")

    assert response.status_code == 422
    assert response.json()["detail"] == "date_from must be on or before date_to."
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


def test_category_lifecycle_audit_has_actor_target_values_and_timestamp(db, admin_user):
    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/config/categories",
            "headers": [],
            "client": ("127.0.0.1", 12345),
            "server": ("testserver", 80),
            "scheme": "http",
            "query_string": b"",
        }
    )
    created = create_category(
        CategoryCreate(name="Audit lifecycle test", description="created"),
        request=request,
        db=db,
        current_user=admin_user,
    )
    category_id = created["id"]

    update_category(
        category_id,
        CategoryCreate(name="Audit lifecycle test", description="updated"),
        request=request,
        db=db,
        current_user=admin_user,
    )
    delete_category(
        category_id,
        request=request,
        db=db,
        current_user=admin_user,
    )

    rows = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_name == "SpendingCategory",
            AuditLog.record_id == str(category_id),
        )
        .order_by(AuditLog.audit_id)
        .all()
    )

    assert [row.action_type for row in rows] == ["CREATE", "UPDATE", "DELETE"]
    assert all(row.user_id == admin_user.user_id for row in rows)
    assert all(row.created_at is not None for row in rows)
    assert rows[0].old_value is None
    assert rows[0].new_value["description"] == "created"
    assert rows[1].old_value["description"] == "created"
    assert rows[1].new_value["description"] == "updated"
    assert rows[2].old_value["description"] == "updated"
    assert rows[2].new_value is None
