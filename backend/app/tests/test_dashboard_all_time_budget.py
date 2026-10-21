"""
Dashboard "All time" Total Budget (period_id=0) was $0: /api/config/labgroups
treated 0 as a literal period id. 0 now means all fiscal years, the same as
/api/dashboard/breakdown. Runs inside the conftest.db savepoint.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import func

import app.api.dashboard as dashboard_api
from app.api.config import get_lab_groups
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup
from app.models.staging import PurchaseRequest, PurchaseRequestLine


@pytest.fixture
def two_year_group(db):
    """A lab group with budgets in two fiscal years and spend in and out of them."""
    periods = db.query(BudgetPeriod).order_by(BudgetPeriod.start_date).all()
    while len(periods) < 2:
        year = 2090 + len(periods)
        period = BudgetPeriod(
            period_name=f"FY-TEST-{year}",
            year_no=year,
            start_date=date(year, 4, 1),
            end_date=date(year + 1, 3, 31),
        )
        db.add(period)
        db.flush()
        periods.append(period)
    p1, p2 = periods[0], periods[1]

    group = LabGroup(lab_group_name="ALLTIME-TEST", wbs_code="WBS-ALLTIME-TEST")
    db.add(group)
    db.flush()
    lab = Lab(
        lab_group_id=group.lab_group_id,
        lab_code="AT-TEST-01",
        lab_name="All-time Test Lab",
    )
    db.add(lab)
    db.flush()

    for period, envelope, allocated in ((p1, "1000", "400"), (p2, "2500", "600")):
        db.add(
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                budget_amount=Decimal(envelope),
                updated_at=func.now(),
            )
        )
        db.add(
            Budget(
                period_id=period.period_id,
                lab_group_id=group.lab_group_id,
                lab_id=lab.lab_id,
                budget_amount=Decimal(allocated),
                updated_at=func.now(),
            )
        )

    # 70 inside p1, 30 before any fiscal year.
    for pr_no, when, amount in (
        ("PR-ALLTIME-IN", p1.start_date, "70"),
        ("PR-ALLTIME-OUT", date(2000, 1, 1), "30"),
    ):
        pr = PurchaseRequest(source_pr_number=pr_no, request_date=when)
        db.add(pr)
        db.flush()
        db.add(
            PurchaseRequestLine(
                pr_id=pr.pr_id,
                lab_id=lab.lab_id,
                amount_gst=Decimal(amount),
                currency_code="SGD",
                pr_status="Approved",
            )
        )
    db.flush()
    return {"group_id": group.lab_group_id, "p1": p1.period_id, "p2": p2.period_id}


def _group(rows, group_id):
    return next(row for row in rows if row["id"] == group_id)


def test_all_time_sums_every_fiscal_year(db, admin_user, two_year_group):
    row = _group(get_lab_groups(0, db, admin_user), two_year_group["group_id"])
    assert row["budget"] == 3500.0
    assert row["allocated_to_labs"] == 1000.0
    assert row["unallocated"] == 2500.0
    assert row["spent"] == 100.0


def test_single_fiscal_year_unchanged(db, admin_user, two_year_group):
    row = _group(
        get_lab_groups(two_year_group["p1"], db, admin_user),
        two_year_group["group_id"],
    )
    assert row["budget"] == 1000.0
    assert row["allocated_to_labs"] == 400.0
    assert row["spent"] == 70.0

    row = _group(
        get_lab_groups(two_year_group["p2"], db, admin_user),
        two_year_group["group_id"],
    )
    assert row["budget"] == 2500.0
    assert row["allocated_to_labs"] == 600.0


def test_all_time_total_is_sum_of_fiscal_years_for_every_group(db, admin_user):
    periods = [p.period_id for p in db.query(BudgetPeriod).all()]
    all_time = get_lab_groups(0, db, admin_user)
    per_year = [get_lab_groups(pid, db, admin_user) for pid in periods]

    assert sum(g["budget"] for g in all_time) == pytest.approx(
        sum(g["budget"] for rows in per_year for g in rows)
    )
    if any(g["budget"] for rows in per_year for g in rows):
        assert sum(g["budget"] for g in all_time) > 0


def test_dashboard_export_all_time_uses_all_years_budget(db, admin_user, monkeypatch):
    captured = {}

    def fake_workbook(meta, kpis, *args):
        captured["meta"] = meta
        captured["kpis"] = kpis
        from io import BytesIO

        return BytesIO(b"")

    monkeypatch.setattr(dashboard_api, "build_dashboard_workbook", fake_workbook)
    dashboard_api.export_dashboard(
        date_range="all",
        start_date=None,
        end_date=None,
        period_id=0,
        lab_group_id=None,
        lab_id=None,
        custom_start="",
        custom_end="",
        db=db,
        current_user=admin_user,
    )

    expected = sum(g["budget"] for g in get_lab_groups(0, db, admin_user))
    assert captured["meta"].fy_label == "All time"
    assert float(captured["kpis"].total_budget) == pytest.approx(expected)
    assert expected > 0
