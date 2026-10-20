from datetime import date, datetime
from decimal import Decimal
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.main import app
from app.api.alerts import _find_threshold_crossing
from app.database import get_db
from app.dependencies.auth import get_current_user
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


def test_threshold_crossing_uses_commit_order_and_exact_line():
    early_batch = UploadBatch(
        batch_id=1,
        uploaded_by=1,
        filename="early.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 5, 1, 9, 0),
    )
    later_batch = UploadBatch(
        batch_id=2,
        uploaded_by=1,
        filename="later.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 6, 1, 9, 0),
    )
    early_commit_pr = PurchaseRequest(
        pr_id=1,
        latest_batch_id=1,
        source_pr_number="PR-LATER-DATE",
        request_date=date(2099, 7, 1),
    )
    later_commit_pr = PurchaseRequest(
        pr_id=2,
        latest_batch_id=2,
        source_pr_number="PR-EARLIER-DATE",
        request_date=date(2099, 4, 1),
    )
    first_line = PurchaseRequestLine(
        pr_line_id=1, pr_id=1, line_no=1, amount_gst=Decimal("500.00")
    )
    before_crossing = PurchaseRequestLine(
        pr_line_id=2, pr_id=2, line_no=1, amount_gst=Decimal("200.00")
    )
    crossing_line = PurchaseRequestLine(
        pr_line_id=3, pr_id=2, line_no=2, amount_gst=Decimal("150.00")
    )

    batch_id, line_id = _find_threshold_crossing(
        [
            (crossing_line, later_commit_pr, later_batch),
            (first_line, early_commit_pr, early_batch),
            (before_crossing, later_commit_pr, later_batch),
        ],
        Decimal("1000.00"),
        80,
    )

    assert batch_id == later_batch.batch_id
    assert line_id == crossing_line.pr_line_id


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
    and emails only the responsible active Team Leads.
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
            query_mock.filter.return_value.all.return_value = [fake_lead]
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
    assert recipients == ["dept_lead@test.com"]
    assert "dept_lead@test.com" in recipients

    assert "95%" in args[1]
    assert "CRITICAL" in args[1]
    assert "Test Engineering Department" in args[1]


# ─── W17-01B Alert Drill-Down Tests (/api/alerts/drilldown) ──────────────
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

    # Create three batches:
    # - batch1 ($500 on May 1 -> 50% cumulative)
    # - batch2 ($350 on Jun 1 -> 85% cumulative: crosses 80% threshold!)
    # - batch3 ($50  on Jul 1 -> 90% cumulative: post-crossing batch still in 80% bracket)
    batch1 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch1.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 5, 1, 9, 0),
    )
    batch2 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch2.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 6, 1, 9, 0),
    )
    batch3 = UploadBatch(
        uploaded_by=uploader.user_id,
        filename="batch3.xlsx",
        file_type="xlsx",
        upload_status="committed",
        processed_at=datetime(2099, 7, 1, 9, 0),
    )
    db.add_all([batch1, batch2, batch3])
    db.flush()

    pr1 = PurchaseRequest(
        source_pr_number="PR-DD-1",
        latest_batch_id=batch1.batch_id,
        requestor_name="Alice",
        # Deliberately later than PR-DD-2: crossing must follow commit order.
        request_date=date(2099, 7, 15),
        grand_total_sgd=Decimal("500.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Approved",
    )
    pr2 = PurchaseRequest(
        source_pr_number="PR-DD-2",
        latest_batch_id=batch2.batch_id,
        requestor_name="Bob",
        request_date=date(2099, 4, 15),
        grand_total_sgd=Decimal("350.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Pending Approval",
    )
    pr3 = PurchaseRequest(
        source_pr_number="PR-DD-3",
        latest_batch_id=batch3.batch_id,
        requestor_name="Charlie",
        request_date=date(2099, 7, 1),
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
        amount_gst=Decimal("200.00"),
        lab_id=lab.lab_id,
        category_id=cat.category_id,
        pr_status="Pending Approval",
    )
    line2b = PurchaseRequestLine(
        pr_id=pr2.pr_id,
        line_no=2,
        item_description="Power Supply Accessories",
        amount_gst=Decimal("150.00"),
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

    # Verify chronological crossing: PR-DD-2 (batch2) crossed 80%, while
    # PR-DD-1 (before 80%) and PR-DD-3 (after 80% was already crossed) are False
    lines_by_key = {
        (line["source_pr_number"], line["line_no"]): line for line in c_data["pr_lines"]
    }
    assert lines_by_key[("PR-DD-1", 1)]["is_triggering_line"] is False
    assert lines_by_key[("PR-DD-2", 1)]["is_triggering_line"] is False
    assert lines_by_key[("PR-DD-2", 2)]["is_triggering_line"] is True
    assert lines_by_key[("PR-DD-3", 1)]["is_triggering_line"] is False

    app.dependency_overrides.clear()
