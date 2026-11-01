from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient
from sqlalchemy import func

from app.main import app
from app.database import get_db
from app.dependencies.auth import get_current_user
from app.api.alerts import _find_threshold_crossing
from app.repositories.persistence_repository import (
    _build_lab_matcher_patterns,
    _detect_labs_in_line,
    _resolve_category_id,
    _split_amount_equally,
)
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
from app.models.upload import PRLineItem
from app.models.auth import User, Role

client = TestClient(app)


def _make_pr_line_item(**overrides: Any) -> PRLineItem:
    """Shared test factory providing all required PRLineItem fields."""
    defaults: dict[str, Any] = {
        "row_number": 1,
        "pr_number": "PR2500001251",
        "pr_sub_date": "2026-06-11",
        "requestor": "jane.tan",
        "req_type": "Maintenance",
        "pr_status": "Pending",
        "po_number": "1000050001",
        "po_status": "COMP",
        "purpose": "E2-02-02",
        "grand_total_sgd": Decimal("5000.00"),
        "item_details": "Price Schedule G Desktop Workstation",
        "quantity": Decimal("1"),
        "unit_rate": Decimal("5000.00"),
        "amount_gst": Decimal("5000.00"),
        "wbs": "D-MOEXX-FCBX-E014-OOE",
        "instruction_to_vendor": "",
        "pr_category": "Maintenance",
        "lab": "",
        "line_identity_key": "PR2500001251::1",
        "content_hash": "testhash1234567890",
    }
    defaults.update(overrides)
    return PRLineItem(**defaults)


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


# ─── Automated Multi-Lab Spending Distribution Tests ─────────────────────
# ─── Automated Multi-Lab Spending Distribution Tests ─────────────────────
def test_multi_lab_detection_and_equal_spending_distribution():
    lab1 = Lab(
        lab_id=101,
        lab_group_id=10,
        lab_code="E2-02-01",
        lab_name="Embedded Systems Lab",
        venue="E2L2R01, Embedded Systems",
        is_general=False,
    )
    lab2 = Lab(
        lab_id=102,
        lab_group_id=10,
        lab_code="E2-02-02",
        lab_name="Robotics Lab",
        venue="E2L2R02, Robotics",
        is_general=False,
    )
    lab3 = Lab(
        lab_id=103,
        lab_group_id=10,
        lab_code="E2-02-03",
        lab_name="Cyber Security Lab",
        venue="E2L2R03, Cyber Security",
        is_general=False,
    )
    patterns = _build_lab_matcher_patterns([lab1, lab2, lab3])

    # 1. Single-lab DivPRReport format (like TL Alert PR 1L.xlsx) stays 1 lab
    single_item = _make_pr_line_item(
        row_number=1,
        pr_number="PR2500001251",
        req_type="Maintenance",
        purpose="E2-02-02",
        item_details="Price Schedule G Desktop Workstation (High End) Latest Gen Intel Core i9 processor",
        amount_gst=Decimal("5000.00"),
        quantity=Decimal("1"),
        unit_rate=Decimal("5000.00"),
    )
    single_detected = _detect_labs_in_line(single_item, patterns)
    assert [lab.lab_id for lab in single_detected] == [102]

    # 2. Multi-lab collective purchase splits equally across all 3 detected labs
    multi_item = _make_pr_line_item(
        row_number=1,
        pr_number="PR-MULTI-001",
        req_type="Consumables",
        purpose="E2-02-01/02/03",
        item_details="Collective purchase of glass flasks for E2-02-01, Robotics Lab, and Cyber Security",
        grand_total_sgd=Decimal("300.00"),
        amount_gst=Decimal("300.00"),
        quantity=Decimal("30"),
        unit_rate=Decimal("10.00"),
        pr_category="Consumables",
        line_identity_key="PR-MULTI-001::1",
    )
    detected = _detect_labs_in_line(multi_item, patterns)
    assert [lab.lab_id for lab in detected] == [101, 102, 103]

    shares_even = _split_amount_equally(multi_item.amount_gst, len(detected))
    assert shares_even == [Decimal("100.00"), Decimal("100.00"), Decimal("100.00")]
    assert sum(shares_even) == Decimal("300.00")

    shares_odd = _split_amount_equally(Decimal("100.00"), len(detected))
    assert shares_odd == [Decimal("33.34"), Decimal("33.33"), Decimal("33.33")]
    assert sum(shares_odd) == Decimal("100.00")

    # 3. Conflicting categories in Req Type ("Maintenance, Consumables") remain flagged (None)
    cats_map = {"general": 1, "maintenance": 2, "consumables": 3}
    conflict_cat_id, conflict_reason = _resolve_category_id(
        item_pr_category=None,
        item_req_type="Maintenance, Consumables",
        classifier_category_id=None,
        classifier_reason=None,
        categories_by_name=cats_map,
        general_cat_id=1,
    )
    assert conflict_cat_id is None
    assert conflict_reason is not None and "Conflicting categories" in conflict_reason

    valid_cat_id, _ = _resolve_category_id(
        item_pr_category=None,
        item_req_type="Maintenance",
        classifier_category_id=None,
        classifier_reason=None,
        categories_by_name=cats_map,
        general_cat_id=1,
    )
    assert valid_cat_id == 2


# ─── Lab Group Creation Guard & Focused Rebudgeting Tests ────────────────
def test_create_lab_group_guards_assigned_orphaned_lab_allocations_and_spending(db):
    uploader = db.query(User).first()
    if not uploader:
        role = db.query(Role).first() or Role(role_name="admin")
        db.add(role)
        db.flush()
        uploader = User(
            role_id=role.role_id,
            full_name="Test Admin",
            email="admin_guard@test.com",
            password_hash="hash",
            is_active=True,
        )
        db.add(uploader)
        db.flush()

    period = BudgetPeriod(
        period_name="FY2098-TEST",
        year_no=2098,
        start_date=date(2098, 4, 1),
        end_date=date(2099, 3, 31),
        is_closed=False,
    )
    db.add(period)
    db.flush()

    cat = SpendingCategory(category_name="Orphaned Lab Category")
    db.add(cat)
    db.flush()

    # Orphaned lab 1 has $6,000 allocated; Orphaned lab 2 has $0 allocated but $4,500 committed spend
    orphan_allocated = Lab(
        lab_group_id=None,
        lab_code="ORPH-01",
        lab_name="Orphaned Allocated Lab",
        is_general=False,
    )
    orphan_spent = Lab(
        lab_group_id=None,
        lab_code="ORPH-02",
        lab_name="Orphaned Spent Lab",
        is_general=False,
    )
    db.add_all([orphan_allocated, orphan_spent])
    db.flush()

    db.add(
        Budget(
            period_id=period.period_id,
            lab_group_id=None,
            lab_id=orphan_allocated.lab_id,
            category_id=cat.category_id,
            budget_amount=Decimal("6000.00"),
            updated_at=func.now(),
        )
    )
    pr = PurchaseRequest(
        source_pr_number="PR-ORPH-1",
        requestor_name="Alice",
        request_date=date(2098, 6, 1),
        grand_total_sgd=Decimal("4500.00"),
        lab_group_id=None,
        pr_status="Pending Approval",
    )
    db.add(pr)
    db.flush()
    db.add(
        PurchaseRequestLine(
            pr_id=pr.pr_id,
            line_no=1,
            item_description="Committed Orphaned Spend",
            amount_gst=Decimal("4500.00"),
            lab_id=orphan_spent.lab_id,
            category_id=cat.category_id,
            pr_status="Pending Approval",
        )
    )
    db.flush()

    admin = User(
        user_id=uploader.user_id,
        email="admin@test.com",
        role_id=1,
        role=MagicMock(role_name="admin"),
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: db

    # 1. Rejects creation when envelope ($5,000) is below selected lab's allocation ($6,000)
    res_low_alloc = client.post(
        f"/api/config/labgroups?period_id={period.period_id}",
        json={
            "name": "Underfunded Group A",
            "wbs_code": "WBS-UF-A",
            "description": "",
            "budget": 5000.0,
            "assigned_lab_ids": [orphan_allocated.lab_id],
        },
    )
    assert res_low_alloc.status_code == 400
    assert "$6,000.00 is already allocated" in res_low_alloc.json()["detail"]
    db.refresh(orphan_allocated)
    assert orphan_allocated.lab_group_id is None

    # 2. Rejects creation when envelope ($3,000) is below selected lab's committed spend ($4,500)
    res_low_spend = client.post(
        f"/api/config/labgroups?period_id={period.period_id}",
        json={
            "name": "Underfunded Group B",
            "wbs_code": "WBS-UF-B",
            "description": "",
            "budget": 3000.0,
            "assigned_lab_ids": [orphan_spent.lab_id],
        },
    )
    assert res_low_spend.status_code == 400
    assert "$4,500.00 has already been spent/utilised" in res_low_spend.json()["detail"]
    db.refresh(orphan_spent)
    assert orphan_spent.lab_group_id is None

    # 3. Succeeds when envelope ($15,000) covers both allocated ($6,000) and spent ($4,500)
    with patch(
        "app.api.config.check_and_notify_lab_group_thresholds"
    ) as mock_group_thresh:
        res_ok = client.post(
            f"/api/config/labgroups?period_id={period.period_id}",
            json={
                "name": "Valid Group",
                "wbs_code": "WBS-VALID-G",
                "description": "",
                "budget": 15000.0,
                "assigned_lab_ids": [orphan_allocated.lab_id, orphan_spent.lab_id],
            },
        )
        assert res_ok.status_code == 200
        body = res_ok.json()
        assert body["budget"] == 15000.0
        assert body["allocated_to_labs"] == 6000.0
        assert body["unallocated"] == 9000.0
        assert body["spent"] == 4500.0
        assert mock_group_thresh.called

    app.dependency_overrides.clear()


def test_rebudgeting_between_ict_and_fcb_categories_and_reconciliation(db):
    uploader = db.query(User).first()
    if not uploader:
        role = db.query(Role).first() or Role(role_name="admin")
        db.add(role)
        db.flush()
        uploader = User(
            role_id=role.role_id,
            full_name="Test Admin",
            email="admin_rebudget@test.com",
            password_hash="hash",
            is_active=True,
        )
        db.add(uploader)
        db.flush()

    period = BudgetPeriod(
        period_name="FY2097-TEST",
        year_no=2097,
        start_date=date(2097, 4, 1),
        end_date=date(2098, 3, 31),
        is_closed=False,
    )
    db.add(period)
    db.flush()

    group = LabGroup(lab_group_name="Rebudget Engineering Group", wbs_code="WBS-RBG")
    db.add(group)
    db.flush()

    lab = Lab(
        lab_group_id=group.lab_group_id,
        lab_code="RBG-01",
        lab_name="Rebudget Systems Lab",
        is_general=False,
    )
    db.add(lab)
    db.flush()

    cat_ict = SpendingCategory(category_name="ICT")
    cat_fcb = SpendingCategory(category_name="FCB")
    cat_overrun = SpendingCategory(category_name="OverrunCat")
    db.add_all([cat_ict, cat_fcb, cat_overrun])
    db.flush()

    # Group Envelope = $20,000
    # Initial Lab Budgets: ICT = $6,000, FCB = $2,000, OverrunCat = $1,000 (Total = $9,000; Unallocated = $11,000)
    db.add_all(
        [
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                lab_id=None,
                category_id=None,
                budget_amount=Decimal("20000.00"),
                updated_at=func.now(),
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                lab_id=lab.lab_id,
                category_id=cat_ict.category_id,
                budget_amount=Decimal("6000.00"),
                updated_at=func.now(),
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                lab_id=lab.lab_id,
                category_id=cat_fcb.category_id,
                budget_amount=Decimal("2000.00"),
                updated_at=func.now(),
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                lab_id=lab.lab_id,
                category_id=cat_overrun.category_id,
                budget_amount=Decimal("1000.00"),
                updated_at=func.now(),
            ),
        ]
    )
    db.flush()

    # Spending in FY2097-TEST:
    # - ICT: $3,000 Approved + $500 Pending = $3,500 committed/projected floor
    # - FCB: $500 Approved
    # - OverrunCat: $1,500 Approved (already in overrun by -$500 against its $1,000 budget)
    pr = PurchaseRequest(
        source_pr_number="PR-RBG-1",
        requestor_name="Bob",
        request_date=date(2097, 7, 15),
        grand_total_sgd=Decimal("5500.00"),
        lab_group_id=group.lab_group_id,
        pr_status="Approved",
    )
    db.add(pr)
    db.flush()

    db.add_all(
        [
            PurchaseRequestLine(
                pr_id=pr.pr_id,
                line_no=1,
                item_description="ICT Server",
                amount_gst=Decimal("3000.00"),
                lab_id=lab.lab_id,
                category_id=cat_ict.category_id,
                pr_status="Approved",
            ),
            PurchaseRequestLine(
                pr_id=pr.pr_id,
                line_no=2,
                item_description="ICT License",
                amount_gst=Decimal("500.00"),
                lab_id=lab.lab_id,
                category_id=cat_ict.category_id,
                pr_status="Pending Approval",
            ),
            PurchaseRequestLine(
                pr_id=pr.pr_id,
                line_no=3,
                item_description="FCB Sensor",
                amount_gst=Decimal("500.00"),
                lab_id=lab.lab_id,
                category_id=cat_fcb.category_id,
                pr_status="Approved",
            ),
            PurchaseRequestLine(
                pr_id=pr.pr_id,
                line_no=4,
                item_description="Emergency Repair",
                amount_gst=Decimal("1500.00"),
                lab_id=lab.lab_id,
                category_id=cat_overrun.category_id,
                pr_status="Approved",
            ),
        ]
    )
    db.flush()

    admin = User(
        user_id=uploader.user_id,
        email="admin@test.com",
        role_id=1,
        role=MagicMock(role_name="admin"),
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_db] = lambda: db

    # 1. Rejects reducing ICT below its $3,500 committed/pending floor ($6,000 -> $3,000)
    res_invalid = client.put(
        f"/api/config/labs/{lab.lab_id}?period_id={period.period_id}",
        json={
            "lab_code": lab.lab_code,
            "lab_name": lab.lab_name,
            "lab_group_id": group.lab_group_id,
            "venue": "",
            "budgets": {
                str(cat_ict.category_id): 3000.0,
                str(cat_fcb.category_id): 5000.0,
                str(cat_overrun.category_id): 1000.0,
            },
        },
    )
    assert res_invalid.status_code == 400
    assert "Cannot reduce 'ICT' budget to $3,000.00" in res_invalid.json()["detail"]
    assert "$3,500.00 has already been spent/utilised" in res_invalid.json()["detail"]

    # 2. Valid move of $2,000 from ICT ($6,000 -> $4,000) to FCB ($2,000 -> $4,000),
    # keeping OverrunCat at $1,000, and adding $1,000 from group unallocated to FCB ($4,000 -> $5,000)
    with (
        patch("app.api.config.check_and_notify_lab_thresholds") as mock_lab_thresh,
        patch(
            "app.api.config.check_and_notify_lab_group_thresholds"
        ) as mock_group_thresh,
    ):
        res_valid = client.put(
            f"/api/config/labs/{lab.lab_id}?period_id={period.period_id}",
            json={
                "lab_code": lab.lab_code,
                "lab_name": lab.lab_name,
                "lab_group_id": group.lab_group_id,
                "venue": "",
                "budgets": {
                    str(cat_ict.category_id): 4000.0,
                    str(cat_fcb.category_id): 5000.0,
                    str(cat_overrun.category_id): 1000.0,
                },
            },
        )
        assert res_valid.status_code == 200
        assert mock_lab_thresh.called
        assert mock_lab_thresh.call_args[0][0] == lab.lab_id
        assert mock_group_thresh.called
        assert mock_group_thresh.call_args[0][0] == group.lab_group_id

    # 3. Verify Lab and Lab Group unallocated values reconcile in /api/config/labgroups
    groups_res = client.get(f"/api/config/labgroups?period_id={period.period_id}")
    assert groups_res.status_code == 200
    grp_cfg = next(g for g in groups_res.json() if g["id"] == group.lab_group_id)
    assert grp_cfg["budget"] == 20000.0
    assert grp_cfg["allocated_to_labs"] == 10000.0
    assert grp_cfg["unallocated"] == 10000.0
    assert grp_cfg["spent"] == 5500.0

    # 4. Verify Dashboard breakdown and Alert drill-down reconcile and preserve negative overrun balance
    dash_res = client.get(
        f"/api/dashboard/breakdown?period_id={period.period_id}&start_date=2097-04-01&end_date=2098-03-31"
    )
    assert dash_res.status_code == 200
    dash_group = next(
        g
        for g in dash_res.json()["lab_groups"]
        if g["lab_group_id"] == group.lab_group_id
    )
    dash_lab = dash_group["labs"][0]
    assert Decimal(dash_lab["budget_sgd"]) == Decimal("10000.00")
    assert Decimal(dash_lab["actual_spend_sgd"]) == Decimal("5000.00")
    assert Decimal(dash_lab["pending_sgd"]) == Decimal("500.00")
    assert Decimal(dash_lab["available_balance_sgd"]) == Decimal("4500.00")

    dash_cats = {c["category_name"]: c for c in dash_lab["categories"]}
    assert Decimal(dash_cats["ICT"]["budget_sgd"]) == Decimal("4000.00")
    assert Decimal(dash_cats["ICT"]["available_balance_sgd"]) == Decimal("500.00")
    assert Decimal(dash_cats["FCB"]["budget_sgd"]) == Decimal("5000.00")
    assert Decimal(dash_cats["FCB"]["available_balance_sgd"]) == Decimal("4500.00")
    # Existing overrun remains visible as -500.00 without corrupting the 4500.00 total
    assert Decimal(dash_cats["OverrunCat"]["budget_sgd"]) == Decimal("1000.00")
    assert Decimal(dash_cats["OverrunCat"]["actual_spend_sgd"]) == Decimal("1500.00")
    assert Decimal(dash_cats["OverrunCat"]["available_balance_sgd"]) == Decimal(
        "-500.00"
    )

    drill_res = client.get(
        f"/api/alerts/drilldown?lab_group_id={group.lab_group_id}&period_id={period.period_id}"
    )
    assert drill_res.status_code == 200
    drill_group = drill_res.json()["lab_groups"][0]
    drill_lab = drill_group["labs"][0]
    assert Decimal(drill_group["envelope_budget_sgd"]) == Decimal("20000.00")
    assert Decimal(drill_group["allocated_lab_budget_sgd"]) == Decimal("10000.00")
    assert Decimal(drill_group["committed_spend_sgd"]) == Decimal("5500.00")
    assert Decimal(drill_lab["budget_sgd"]) == Decimal("10000.00")
    assert Decimal(drill_lab["committed_spend_sgd"]) == Decimal("5500.00")
    assert Decimal(drill_lab["available_balance_sgd"]) == Decimal("4500.00")

    drill_cats = {c["category_name"]: c for c in drill_lab["categories"]}
    assert Decimal(drill_cats["OverrunCat"]["available_balance_sgd"]) == Decimal(
        "-500.00"
    )

    app.dependency_overrides.clear()
