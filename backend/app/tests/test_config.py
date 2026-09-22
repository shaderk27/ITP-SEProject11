from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User


# 1. Setup a Mock User to bypass Authentication
def override_get_current_user():
    return User(
        user_id=1, email="admin@test.com", role_id=1, role=MagicMock(role_name="admin")
    )

app.dependency_overrides[get_current_user] = override_get_current_user

# 2. Setup the Test Client
client = TestClient(app)

def test_create_category():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # Mock duplicate check to return None
    mock_db.query.return_value.filter.return_value.first.return_value = None

    payload = {"name": "Consumables", "description": "Lab supplies"}
    response = client.post("/api/config/categories", json=payload)

    assert response.status_code == 200
    assert response.json()["name"] == "Consumables"
    assert mock_db.add.called is True
    assert mock_db.commit.called is True


@patch("app.api.config.get_or_create_current_period")
def test_get_labs_with_ledger_math(mock_period):
    mock_period.return_value = 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_lab = MagicMock()
    mock_lab.lab_id = 1
    mock_lab.lab_code = "TEST-01"
    mock_lab.lab_name = "Test Lab"
    mock_lab.group.lab_group_name = "Test Group"
    
    mock_query = MagicMock()
    mock_db.query.return_value = mock_query

    # 1. Return the lab for the main query
    mock_query.filter.return_value.all.return_value = [mock_lab]
    
    # 2. Mock scalar returns (Budgets, Spent) to return actual numbers, NOT MagicMocks
    mock_query.filter.return_value.scalar.return_value = 500.0
    mock_query.join.return_value.join.return_value.filter.return_value.scalar.return_value = 500.0
    mock_query.join.return_value.join.return_value.filter.return_value.group_by.return_value.all.return_value = [(2, 500.0)]

    response = client.get("/api/config/labs")

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["spent"] == 500.0


@patch("app.api.config.get_or_create_current_period")
def test_create_lab_exceeds_group_envelope_throws_400(mock_period):
    mock_period.return_value = 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_query = MagicMock()
    mock_db.query.return_value = mock_query

    # 1. Pass the Duplicate Code Check
    mock_query.filter.return_value.first.return_value = None

    # 2. Mock Envelope & Allocated Math (Envelope = 10k, Allocated = 8k)
    mock_query.filter.return_value.scalar.side_effect = [10000.0, 8000.0]

    payload = {
        "lab_code": "TEST-NEW",
        "lab_name": "Overbudget Lab",
        "lab_group_id": 1,
        "budgets": {
            "1": 1500.0, 
            "2": 1000.0  # Total = $2500. Exceeds the $2000 remaining.
        }
    }

    response = client.post("/api/config/labs", json=payload)

    assert response.status_code == 400
    assert "Budget Exceeded" in response.json()["detail"]
    assert mock_db.add.called is False


@patch("app.api.config.get_or_create_current_period")
def test_create_lab_within_group_envelope_succeeds(mock_period):
    mock_period.return_value = 1
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    mock_query = MagicMock()
    mock_db.query.return_value = mock_query

    # 1. Pass the Duplicate Code Check
    mock_query.filter.return_value.first.return_value = None

    # 2. Mock Envelope & Allocated Math (Envelope = 10k, Allocated = 8k)
    mock_query.filter.return_value.scalar.side_effect = [10000.0, 8000.0]

    def mock_refresh(obj):
        obj.lab_id = 99
        obj.group = MagicMock(lab_group_name="Mock Group")

    mock_db.refresh.side_effect = mock_refresh

    payload = {
        "lab_code": "TEST-OK",
        "lab_name": "Underbudget Lab",
        "lab_group_id": 1,
        "budgets": {
            "1": 1500.0 # Total = $1500. Fits within the $2000 remaining.
        }
    }

    response = client.post("/api/config/labs", json=payload)

    assert response.status_code == 200
    assert response.json()["budget"] == 1500.0
    assert mock_db.add.called is True
    assert mock_db.commit.called is True