from fastapi.testclient import TestClient
from unittest.mock import MagicMock, patch
from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.models.auth import User

# 1. Setup a Mock User to bypass Authentication
def override_get_current_user():
    return User(user_id=1, email="admin@test.com", role_id=1, role=MagicMock(role_name="admin"))

app.dependency_overrides[get_current_user] = override_get_current_user

# 2. Setup the Test Client
client = TestClient(app)

def test_create_category():
    # Mock the database session
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db
    
    payload = {
        "name": "Consumables",
        "description": "Lab supplies"
    }
    
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
    
    # 1. Mock the Lab data being returned
    mock_lab = MagicMock()
    mock_lab.lab_id = 1
    mock_lab.lab_code = "TEST-01"
    mock_lab.lab_name = "Test Lab"
    mock_lab.group.lab_group_name = "Test Group"
    mock_db.query.return_value.all.side_effect = [[mock_lab], []] # Returns the lab, then empty budget
    
    # 2. Mock the Ledger Math (func.sum) returning $500 spent
    mock_db.query.return_value.filter.return_value.scalar.return_value = 500.0
    
    # 3. Mock the Group By category query
    mock_db.query.return_value.filter.return_value.group_by.return_value.all.return_value = [(2, 500.0)]
    
    response = client.get("/api/config/labs")
    
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 1
    assert data[0]["spent"] == 500.0
    assert data[0]["spent_by_category"] == {"2": 500.0}