from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.api.alerts import _find_threshold_crossing
from app.services.threshold_service import (
    check_and_notify_lab_thresholds,
    check_and_notify_lab_group_thresholds,
)
from app.models.config import (
    Lab,
    LabGroup,
    LabIcAssignment,
    Budget,
    BudgetPeriod,
    SpendingCategory,
)
from app.models.staging import PurchaseRequest, PurchaseRequestLine, UploadBatch
from app.models.auth import User, Role

client = TestClient(app)


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

    fake_primary_ic = User(email="labic@test.com", role_id=3, is_active=True)
    fake_secondary_ic = User(email="labic2@test.com", role_id=3, is_active=True)
    fake_lead = User(email="lead@test.com", role_id=2, is_active=True)

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
            # 1st call: Lab ICs via join(LabIcAssignment).filter(...).all()
            query_mock.join.return_value.filter.return_value.all.return_value = [
                fake_primary_ic,
                fake_secondary_ic,
            ]
            # 2nd call: Team Leads via filter(...).all()
            query_mock.filter.return_value.all.return_value = [fake_lead]
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
    args, _ = mock_send_email.call_args
    recipients = args[0]
    assert "labic@test.com" in recipients
    assert "labic2@test.com" in recipients
    assert "lead@test.com" in recipients
    assert "80%" in args[1]


@patch("app.services.threshold_service.SessionLocal")
@patch("app.services.threshold_service.send_threshold_alert")
def test_check_and_notify_lab_group_thresholds_95_percent(
    mock_send_email, mock_session_local
):
    """
    Tests that the Top-Down Lab Group Envelope triggers at 95% utilization
    and gathers both the Team Leads and ALL underlying Lab IC emails.
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

    fake_lead = User(email="dept_lead@test.com", role_id=2, is_active=True)
    fake_ic_1 = User(email="ic_lab1@test.com", role_id=3, is_active=True)
    fake_ic_2 = User(email="ic_lab2@test.com", role_id=3, is_active=True)

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
            # 1st call retrieves Team Leads (.all())
            query_mock.filter.return_value.all.return_value = [fake_lead]
            # 2nd call retrieves Lab ICs via lab_ic_assignments -> labs (.all())
            query_mock.join.return_value.join.return_value.filter.return_value.all.return_value = [
                fake_ic_1,
                fake_ic_2,
            ]
        else:
            query_mock.filter.return_value.scalar = scalar_mock
            query_mock.join.return_value.join.return_value.filter.return_value.scalar = scalar_mock
        return query_mock

    mock_db.query.side_effect = mock_query_side_effect

    check_and_notify_lab_group_thresholds(10)

    assert fake_group.notified_95 is True
    assert fake_group.notified_100 is False
    assert mock_db.commit.called is True

    mock_send_email.assert_called_once()
    args, _ = mock_send_email.call_args

    recipients = args[0]
    assert len(recipients) == 3
    assert "dept_lead@test.com" in recipients
    assert "ic_lab1@test.com" in recipients
    assert "ic_lab2@test.com" in recipients

    assert "95%" in args[1]
    assert "CRITICAL" in args[1]
    assert "Test Engineering Department" in args[1]


# ─── W17-01B Alert Drill-Down Tests (/api/alerts/drilldown) ──────────────
def test_find_threshold_crossing_uses_upload_batch_chronology_and_exact_line():
    batch_early = UploadBatch(
        batch_id=10,
        uploaded_at=datetime(2026, 5, 1, 9, 0, tzinfo=timezone.utc),
        processed_at=datetime(2026, 5, 1, 9, 5, tzinfo=timezone.utc),
    )
    batch_trigger = UploadBatch(
        batch_id=20,
        uploaded_at=datetime(2026, 5, 2, 9, 0, tzinfo=timezone.utc),
        processed_at=datetime(2026, 5, 2, 9, 5, tzinfo=timezone.utc),
    )
    # Uploaded last, even though its PR has an older historical request_date
    batch_late_with_old_pr_date = UploadBatch(
        batch_id=30,
        uploaded_at=datetime(2026, 5, 3, 9, 0, tzinfo=timezone.utc),
        processed_at=datetime(2026, 5, 3, 9, 5, tzinfo=timezone.utc),
    )

    pr1 = PurchaseRequest(pr_id=1, latest_batch_id=10, request_date=date(2026, 5, 1))
    pr2 = PurchaseRequest(pr_id=2, latest_batch_id=20, request_date=date(2026, 5, 2))
    pr3 = PurchaseRequest(pr_id=3, latest_batch_id=30, request_date=date(2026, 4, 1))

    line1 = PurchaseRequestLine(
        pr_line_id=101, pr_id=1, line_no=1, amount_gst=Decimal("500.00")
    )
    # Crosses 80% ($820 / $1000)
    line2a = PurchaseRequestLine(
        pr_line_id=201, pr_id=2, line_no=1, amount_gst=Decimal("320.00")
    )
    # Same batch, after 80% was already crossed ($850 / $1000)
    line2b = PurchaseRequestLine(
        pr_line_id=202, pr_id=2, line_no=2, amount_gst=Decimal("30.00")
    )
    line3 = PurchaseRequestLine(
        pr_line_id=301, pr_id=3, line_no=1, amount_gst=Decimal("50.00")
    )

    items = [
        (line3, pr3, batch_late_with_old_pr_date),
        (line2b, pr2, batch_trigger),
        (line1, pr1, batch_early),
        (line2a, pr2, batch_trigger),
    ]

    trigger_batch_id, trigger_line_id = _find_threshold_crossing(
        items, Decimal("1000.00"), 80
    )
    assert trigger_batch_id == 20
    assert trigger_line_id == 201


def test_alert_drilldown_rbac_blocks_unauthorized_teamlead_and_labic():
    mock_db = MagicMock()
    app.dependency_overrides[get_db] = lambda: mock_db

    # 1. Team Lead assigned to Group 10 tries to drill down into Group 99 -> 403
    teamlead = User(
        user_id=2,
        email="tl@test.com",
        role_id=2,
        lab_group_id=10,
        role=MagicMock(role_name="teamlead"),
    )
    app.dependency_overrides[get_current_user] = lambda: teamlead
    res_tl = client.get("/api/alerts/drilldown?lab_group_id=99")
    assert res_tl.status_code == 403

    # 2. Lab IC assigned to Lab 5 tries to drill down into Lab 88 -> 403
    labic = User(
        user_id=3,
        email="ic@test.com",
        role_id=3,
        role=MagicMock(role_name="labic"),
    )
    assignment = LabIcAssignment(lab_id=5, user_id=3, is_primary=True)
    labic.lab_assignments = [assignment]
    app.dependency_overrides[get_current_user] = lambda: labic
    res_ic = client.get("/api/alerts/drilldown?lab_id=88")
    assert res_ic.status_code == 403

    app.dependency_overrides.clear()


def test_alert_drilldown_reconciles_calculations_and_flags_triggering_lines(db):
    # Ensure a valid user exists for UploadBatch foreign key
    uploader = db.query(User).first()
    if not uploader:
        role = db.query(Role).first()
        if not role:
            role = Role(role_name="admin")
            db.add(role)
            db.flush()
        uploader = User(
            role_id=role.role_id,
            full_name="Test Admin",
            email="test_uploader@test.com",
            password_hash="hash",
            is_active=True,
        )
        db.add(uploader)
        db.flush()

    period = BudgetPeriod(
        period_name="FY2099-TEST",
        year_no=2099,
        start_date=date(2099, 4, 1),
        end_date=date(2100, 3, 31),
        is_closed=False,
    )
    db.add(period)
    db.flush()

    group = LabGroup(lab_group_name="Drilldown Group", wbs_code="WBS-DD")
    db.add(group)
    db.flush()

    lab = Lab(
        lab_group_id=group.lab_group_id,
        lab_code="DD-01",
        lab_name="Drilldown Lab",
        is_general=False,
    )
    db.add(lab)
    db.flush()

    cat = SpendingCategory(category_name="Drilldown Equipment")
    db.add(cat)
    db.flush()

    # Envelope = $1,000; Lab Category Budget = $1,000
    db.add(
        Budget(
            period_id=period.period_id,
            lab_group_id=group.lab_group_id,
            lab_id=None,
            category_id=None,
            budget_amount=Decimal("1000.00"),
            updated_at=func.now(),
        )
    )
    db.add(
        Budget(
            period_id=period.period_id,
            lab_group_id=group.lab_group_id,
            lab_id=lab.lab_id,
            category_id=cat.category_id,
            budget_amount=Decimal("1000.00"),
            updated_at=func.now(),
        )
    )
    db.flush()

    # Create three batches in commit chronology:
    # - batch1 ($500 -> 50% cumulative)
    # - batch2 (line2a $320 -> 82% cumulative crosses 80%; line2b $30 -> 85% in same batch)
    # - batch3 ($50 -> 90% cumulative, with an older request_date to verify commit chronology wins)
    batch1 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch1.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 5, 1, 10, 0, tzinfo=timezone.utc),
    )
    batch2 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch2.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 6, 1, 10, 0, tzinfo=timezone.utc),
    )
    batch3 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch3.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 7, 1, 10, 0, tzinfo=timezone.utc),
    )
    db.add_all([batch1, batch2, batch3])
    db.flush()

    pr1 = PurchaseRequest(
        source_pr_number="PR-DD-1",
        latest_batch_id=batch1.batch_id,
        requestor_name="Alice",
        request_date=date(2099, 5, 1),
        grand_total_sgd=Decimal("500.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Approved",
    )
    pr2 = PurchaseRequest(
        source_pr_number="PR-DD-2",
        latest_batch_id=batch2.batch_id,
        requestor_name="Bob",
        request_date=date(2099, 6, 1),
        grand_total_sgd=Decimal("350.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Pending Approval",
    )
    pr3 = PurchaseRequest(
        source_pr_number="PR-DD-3",
        latest_batch_id=batch3.batch_id,
        requestor_name="Charlie",
        request_date=date(2099, 4, 15),
        grand_total_sgd=Decimal("50.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Approved",
    )
    db.add_all([pr1, pr2, pr3])
    db.flush()

    line1 = PurchaseRequestLine(
        pr_id=pr1.pr_id,
        line_no=1,
        item_description="Oscilloscope",
        amount_gst=Decimal("500.00"),
        lab_id=lab.lab_id,
        category_id=cat.category_id,
        pr_status="Approved",
    )
    line2a = PurchaseRequestLine(
        pr_id=pr2.pr_id,
        line_no=1,
        item_description="Power Supply",
        amount_gst=Decimal("320.00"),
        lab_id=lab.lab_id,
        category_id=cat.category_id,
        pr_status="Pending Approval",
    )
    line2b = PurchaseRequestLine(
        pr_id=pr2.pr_id,
        line_no=2,
        item_description="Power Supply Cable",
        amount_gst=Decimal("30.00"),
        lab_id=lab.lab_id,
        category_id=cat.category_id,
        pr_status="Pending Approval",
    )
    line3 = PurchaseRequestLine(
        pr_id=pr3.pr_id,
        line_no=1,
        item_description="Multimeter Leads",
        amount_gst=Decimal("50.00"),
        lab_id=lab.lab_id,
        category_id=cat.category_id,
        pr_status="Approved",
    )
    db.add_all([line1, line2a, line2b, line3])
    db.flush()

    admin = User(
        user_id=uploader.user_id,
        email="admin@test.com",
        role_id=1,
        role=MagicMock(role_name="admin"),
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: db

    res = client.get(
        f"/api/alerts/drilldown?lab_group_id={group.lab_group_id}&period_id={period.period_id}"
    )
    assert res.status_code == 200
    payload = res.json()
    assert len(payload["lab_groups"]) == 1

    g_data = payload["lab_groups"][0]
    assert Decimal(g_data["envelope_budget_sgd"]) == Decimal("1000.00")
    assert Decimal(g_data["actual_spend_sgd"]) == Decimal("550.00")
    assert Decimal(g_data["pending_sgd"]) == Decimal("350.00")
    assert Decimal(g_data["committed_spend_sgd"]) == Decimal("900.00")
    assert g_data["threshold_reached"] == 80
    assert g_data["triggering_batch_id"] == batch2.batch_id

    l_data = g_data["labs"][0]
    assert l_data["lab_id"] == lab.lab_id
    assert Decimal(l_data["committed_spend_sgd"]) == Decimal("900.00")
    assert l_data["threshold_reached"] == 80
    assert l_data["triggering_batch_id"] == batch2.batch_id

    c_data = l_data["categories"][0]
    assert c_data["category_id"] == cat.category_id
    assert len(c_data["pr_lines"]) == 4

    # Only line2a (which crossed 80%) is True; line2b in the same batch is False
    lines_by_id = {line["pr_line_id"]: line for line in c_data["pr_lines"]}
    assert lines_by_id[line1.pr_line_id]["is_triggering_line"] is False
    assert lines_by_id[line2a.pr_line_id]["is_triggering_line"] is True
    assert lines_by_id[line2b.pr_line_id]["is_triggering_line"] is False
    assert lines_by_id[line3.pr_line_id]["is_triggering_line"] is False

    app.dependency_overrides.clear()
