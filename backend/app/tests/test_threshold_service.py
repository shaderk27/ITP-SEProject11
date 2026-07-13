from unittest.mock import MagicMock, patch
from datetime import date
from app.services.threshold_service import check_and_notify_lab_thresholds
from app.models.config import Lab, BudgetPeriod
from app.models.auth import User


@patch("app.services.threshold_service.SessionLocal")
@patch("app.services.threshold_service.send_threshold_alert")
def test_check_and_notify_lab_thresholds_80_percent(
    mock_send_email, mock_session_local
):
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    fake_lab = Lab(
        lab_id=1,
        lab_group_id=10,
        lab_name="Test Lab",
        lab_code="TEST-1",
        notified_50=True,
        notified_80=False,
        notified_95=False,
        notified_100=False,
        alert_period_id=1,  # Matching our mock period
    )

    fake_period = BudgetPeriod(
        period_id=1, start_date=date(2020, 1, 1), end_date=date(2099, 12, 31)
    )

    fake_ic = User(email="labic@test.com", role_id=3)
    fake_lead = User(email="lead@test.com", role_id=2)

    scalar_mock = MagicMock(side_effect=[1000, 850])

    def mock_query_side_effect(*args, **kwargs):
        query_mock = MagicMock()
        model = args[0]

        if model is Lab:
            query_mock.filter.return_value.first.return_value = fake_lab
        elif model is BudgetPeriod:
            query_mock.filter.return_value.first.return_value = fake_period
        elif model is User:
            query_mock.filter.return_value.first.side_effect = [fake_ic, fake_lead]
        else:
            # Handle both direct filters and join().filter() chains
            query_mock.filter.return_value.scalar = scalar_mock
            query_mock.join.return_value.filter.return_value.scalar = scalar_mock

        return query_mock

    mock_db.query.side_effect = mock_query_side_effect

    check_and_notify_lab_thresholds(1)

    assert fake_lab.notified_80 is True
    assert mock_db.commit.called is True
    mock_send_email.assert_called_once()
