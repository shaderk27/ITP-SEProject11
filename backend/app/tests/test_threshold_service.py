from unittest.mock import MagicMock, patch

from app.services.threshold_service import check_and_notify_lab_thresholds
from app.models.config import Lab
from app.models.auth import User

# The @patch decorator completely intercepts the email function so we don't accidentally send real emails!
@patch("app.services.threshold_service.send_threshold_alert")
def test_check_and_notify_lab_thresholds_80_percent(mock_send_email):
    # 1. Create a Mock Database Session
    mock_db = MagicMock()
    
    # 2. Setup the Fake Lab (Already notified at 50%, but not 80% yet)
    fake_lab = Lab(
        lab_id=1, 
        lab_group_id=10, 
        lab_name="Test Lab", 
        lab_code="TEST-1", 
        notified_50=True, 
        notified_80=False, 
        notified_95=False
    )
    
    # 3. Setup Fake Users
    fake_ic = User(email="labic@test.com", role_id=3)
    fake_lead = User(email="lead@test.com", role_id=2)
    
    # 4. Control what the DB returns when the function asks for data
    def mock_query_side_effect(model):
        query_mock = MagicMock()
        
        if model == Lab:
            query_mock.filter.return_value.first.return_value = fake_lab
        elif model == User:
            # We query the User table twice (Once for IC, once for Team Lead)
            query_mock.filter.return_value.first.side_effect = [fake_ic, fake_lead]
        else:
            # For func.sum queries (Budget and PurchaseRequestLine)
            # We tell the mock DB: The budget is $1,000, and $850 is spent (85% utilization)
            query_mock.filter.return_value.scalar.side_effect = [1000, 850] 
            
        return query_mock

    # Attach our custom rules to the mock database
    mock_db.query.side_effect = mock_query_side_effect

    # 5. Run the function
    check_and_notify_lab_thresholds(mock_db, 1)

    # 6. Assertions (Did the code do what it was supposed to do?)
    
    # Proof the anti-spam flag was updated
    assert fake_lab.notified_80 is True
    assert mock_db.commit.called is True
    
    # Proof the email function was called exactly once
    mock_send_email.assert_called_once()
    
    # Extract the arguments passed to the email function
    args, kwargs = mock_send_email.call_args
    recipients = args[0]
    subject = args[1]
    
    # Proof the correct people were emailed with the correct subject line
    assert "labic@test.com" in recipients
    assert "lead@test.com" in recipients
    assert "80% Budget Utilization" in subject