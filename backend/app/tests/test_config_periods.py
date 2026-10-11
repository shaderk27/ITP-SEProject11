"""
Multi-fiscal-year budget tests (W11-04): fiscal-year creation and the critical
guarantee that editing one FY's lab budget does not wipe another FY's budget.

Each test runs in a SAVEPOINT (conftest.db) so its writes never persist — even
though create_lab/update_lab call db.commit() internally.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException, BackgroundTasks

from app.api.config import (
    PeriodCreate,
    create_lab,
    create_period,
    get_lab_groups,
    update_lab,
)
from app.models.config import Budget, LabCreate, LabGroup, SpendingCategory


def _group_and_category(db):
    group = db.query(LabGroup).filter(LabGroup.lab_group_name != "General").first()
    category = db.query(SpendingCategory).first()
    if group is None or category is None:
        pytest.skip("Seed data missing; run dev_seed.sql.")
    return group, category


def test_create_period_derives_april_to_march(db):
    result = create_period(PeriodCreate(year=2040), db=db)
    assert result["name"] == "FY2040"
    assert result["year"] == 2040
    assert result["start_date"] == "2040-04-01"
    assert result["end_date"] == "2041-03-31"


def test_create_period_rejects_duplicate(db):
    create_period(PeriodCreate(year=2041), db=db)
    with pytest.raises(HTTPException) as exc:
        create_period(PeriodCreate(year=2041), db=db)
    assert exc.value.status_code == 400


def test_update_lab_only_clears_the_selected_fiscal_year(db):
    """The delete in update_lab is scoped to the target period, so setting a new
    year's budget leaves other years' budgets intact."""
    group, category = _group_and_category(db)
    cat_key = str(category.category_id)

    fy_a = create_period(PeriodCreate(year=2050), db=db)["id"]
    fy_b = create_period(PeriodCreate(year=2051), db=db)["id"]
    # Labs are funded from the group's envelope, so each FY needs one.
    for fy in (fy_a, fy_b):
        db.add(
            Budget(
                period_id=fy,
                lab_group_id=group.lab_group_id,
                budget_amount=Decimal("100000.00"),
                updated_at=datetime.now(timezone.utc),
            )
        )
    db.flush()

    lab = create_lab(
        lab_in=LabCreate(
            lab_code="W11T-FY",
            lab_name="W11 FY Test Lab",
            lab_group_id=group.lab_group_id,
            budgets={cat_key: 1000.0},
        ),
        period_id=fy_a,
        db=db,
    )
    lab_id = lab["id"]

    # Set a different budget for FY-B — must not touch FY-A.
    update_lab(
        lab_id=lab_id,
        lab_in=LabCreate(
            lab_code="W11T-FY",
            lab_name="W11 FY Test Lab",
            lab_group_id=group.lab_group_id,
            budgets={cat_key: 7000.0},
        ),
        background_tasks=BackgroundTasks(),  # Added the required background_tasks object
        period_id=fy_b,
        db=db,
    )

    fy_a_budget = sum(
        b.budget_amount
        for b in db.query(Budget)
        .filter(Budget.lab_id == lab_id, Budget.period_id == fy_a)
        .all()
    )
    fy_b_budget = sum(
        b.budget_amount
        for b in db.query(Budget)
        .filter(Budget.lab_id == lab_id, Budget.period_id == fy_b)
        .all()
    )
    assert fy_a_budget == Decimal("1000.00")  # intact
    assert fy_b_budget == Decimal("7000.00")  # newly set


def test_lab_groups_budget_scoped_to_period(db, admin_user):
    """The /labgroups Allocated Budget total (which feeds the dashboard's Total
    Budget card) reflects only the requested fiscal year, not a sum across
    years. Guards the contract the frontend relies on for FY scoping."""
    group, category = _group_and_category(db)
    fy_a = create_period(PeriodCreate(year=2060), db=db)["id"]
    fy_b = create_period(PeriodCreate(year=2061), db=db)["id"]
    now = datetime.now(timezone.utc)
    db.add_all(
        [
            Budget(
                period_id=fy_a,
                lab_group_id=group.lab_group_id,
                category_id=category.category_id,
                budget_amount=Decimal("1000"),
                created_at=now,
                updated_at=now,
            ),
            Budget(
                period_id=fy_b,
                lab_group_id=group.lab_group_id,
                category_id=category.category_id,
                budget_amount=Decimal("5000"),
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.flush()

    groups_a = get_lab_groups(period_id=fy_a, db=db, current_user=admin_user)
    g_a = next(g for g in groups_a if g["id"] == group.lab_group_id)
    assert Decimal(str(g_a["budget"])) == Decimal("1000")

    groups_b = get_lab_groups(period_id=fy_b, db=db, current_user=admin_user)
    g_b = next(g for g in groups_b if g["id"] == group.lab_group_id)
    assert Decimal(str(g_b["budget"])) == Decimal("5000")
