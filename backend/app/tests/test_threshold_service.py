from unittest.mock import MagicMock, patch
from datetime import date
from app.services.threshold_service import (
    check_and_notify_lab_thresholds,
    check_and_notify_lab_group_thresholds,
)
from app.models.config import Lab, LabGroup, BudgetPeriod
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
        alert_period_id=1,
    )

    fake_period = BudgetPeriod(
        period_id=1, start_date=date(2020, 1, 1), end_date=date(2099, 12, 31)
    )

    fake_ic = User(email="labic@test.com", role_id=3)
    fake_lead = User(email="lead@test.com", role_id=2)

    # Budget is 1000, Spent is 850 (85%)
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
            query_mock.filter.return_value.scalar = scalar_mock
            query_mock.join.return_value.filter.return_value.scalar = scalar_mock
        return query_mock

    mock_db.query.side_effect = mock_query_side_effect

    check_and_notify_lab_thresholds(1)

    assert fake_lab.notified_80 is True
    assert fake_lab.notified_95 is False
    assert mock_db.commit.called is True
    mock_send_email.assert_called_once()
    args, kwargs = mock_send_email.call_args
    assert "80%" in args[1]


@patch("app.services.threshold_service.SessionLocal")
@patch("app.services.threshold_service.send_threshold_alert")
def test_check_and_notify_lab_group_thresholds_95_percent(
    mock_send_email, mock_session_local
):
    """
    Tests that the Top-Down Lab Group Envelope triggers at 95% utilization
    and successfully gathers both the Team Lead and ALL underlying Lab IC emails.
    """
    mock_db = MagicMock()
    mock_session_local.return_value.__enter__.return_value = mock_db

    fake_group = LabGroup(
        lab_group_id=10,
        lab_group_name="Test Engineering Department",
        wbs_code="WBS-ENG",
        notified_50=True,
        notified_80=True,
        notified_95=False,
        notified_100=False,
        alert_period_id=1,
    )

    fake_period = BudgetPeriod(
        period_id=1, start_date=date(2020, 1, 1), end_date=date(2099, 12, 31)
    )

    fake_lead = User(email="dept_lead@test.com", role_id=2)
    fake_ic_1 = User(email="ic_lab1@test.com", role_id=3)
    fake_ic_2 = User(email="ic_lab2@test.com", role_id=3)

    # Master Envelope is 100,000, Total Department Spent is 97,000 (97%)
    scalar_mock = MagicMock(side_effect=[100000, 97000])

    def mock_query_side_effect(*args, **kwargs):
        query_mock = MagicMock()
        model = args[0]
        if model is LabGroup:
            query_mock.filter.return_value.first.return_value = fake_group
        elif model is BudgetPeriod:
            query_mock.filter.return_value.first.return_value = fake_period
        elif model is User:
            # 1st call retrieves Team Lead (.first())
            query_mock.filter.return_value.first.return_value = fake_lead
            # 2nd call retrieves Lab ICs using a Join (.all())
            query_mock.join.return_value.filter.return_value.all.return_value = [
                fake_ic_1,
                fake_ic_2,
            ]
        else:
            # Budget and Spend queries
            query_mock.filter.return_value.scalar = scalar_mock
            query_mock.join.return_value.join.return_value.filter.return_value.scalar = scalar_mock
        return query_mock

    mock_db.query.side_effect = mock_query_side_effect

    check_and_notify_lab_group_thresholds(10)

    assert fake_group.notified_95 is True
    assert fake_group.notified_100 is False
    assert mock_db.commit.called is True

    mock_send_email.assert_called_once()
    args, kwargs = mock_send_email.call_args

    # Assert email sent to the 3 combined users without duplicates
    recipients = args[0]
    assert len(recipients) == 3
    assert "dept_lead@test.com" in recipients
    assert "ic_lab1@test.com" in recipients

    # Assert proper context in the email
    assert "95%" in args[1]
    assert "CRITICAL" in args[1]
    assert "Test Engineering Department" in args[1]
