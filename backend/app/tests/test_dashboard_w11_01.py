"""
W11-01 done-gate tests: spending aggregation + budget utilization calculations
by Lab and category (the dashboard calculation engine).

Covers the guide's Minimum Testing section:
  1. Calculation tests on small *known* datasets.
  2. Integration test over stored budget + purchase data (nested roll-up).
  3. Boundary tests: zero budget, missing-category line.
Plus the locked spec rules (General excluded) and role scoping.

Determinism note: the dashboard endpoints aggregate the WHOLE database, so
each test builds its own freshly-created lab_group / lab / category and asserts
only on *that* group's subtree. The conftest `db` fixture wraps everything in a
SAVEPOINT, so none of these inserts persist to budget_system.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.dashboard import get_breakdown, get_spending_summary
from app.models.auth import Role, User
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine

# Unique-ish suffix base so repeated entity names never collide inside a run.
_SEQ = {"n": 0}


def _next_suffix() -> str:
    _SEQ["n"] += 1
    return f"{_SEQ['n']:04d}"


# ─── Builders (all rolled back by the savepoint) ─────────────────────────
def _make_group(db, name: str | None = None) -> LabGroup:
    suffix = _next_suffix()
    group = LabGroup(
        lab_group_name=name or f"W11T_GRP_{suffix}",
        wbs_code=f"WBS-W11T-{suffix}",
    )
    db.add(group)
    db.flush()
    return group


def _make_lab(db, group: LabGroup) -> Lab:
    suffix = _next_suffix()
    lab = Lab(
        lab_group_id=group.lab_group_id,
        lab_code=f"W11T-L{suffix}",
        lab_name=f"W11 Test Lab {suffix}",
    )
    db.add(lab)
    db.flush()
    return lab


def _make_category(db) -> SpendingCategory:
    suffix = _next_suffix()
    cat = SpendingCategory(category_name=f"W11 Test Cat {suffix}")
    db.add(cat)
    db.flush()
    return cat


def _a_period_id(db) -> int:
    """budgets.period_id is NOT NULL in the DB, so reuse a seeded period."""
    period = db.query(BudgetPeriod).order_by(BudgetPeriod.period_id).first()
    if period is None:
        pytest.skip("No budget_periods seeded; run dev_seed.sql.")
    return period.period_id


def _set_budget(db, group, lab, category, amount) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        Budget(
            period_id=_a_period_id(db),
            lab_group_id=group.lab_group_id,
            lab_id=lab.lab_id,
            category_id=category.category_id if category else None,
            budget_amount=Decimal(str(amount)),
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()


def _add_line(db, lab, category, amount, pr_status: str) -> None:
    """Insert one committed PR + line with a known amount/status/lab/category."""
    suffix = _next_suffix()
    pr = PurchaseRequest(
        source_pr_number=f"PR-W11T-{suffix}",
        grand_total_sgd=Decimal(str(amount)),
        pr_status=pr_status,
    )
    db.add(pr)
    db.flush()
    db.add(
        PurchaseRequestLine(
            pr_id=pr.pr_id,
            line_no=1,
            item_description=f"W11 test line {suffix}",
            amount_gst=Decimal(str(amount)),
            currency_code="SGD",
            lab_id=lab.lab_id,
            category_id=category.category_id if category else None,
            pr_status=pr_status,
        )
    )
    db.flush()


def _role(db, name: str) -> Role | None:
    for r in db.query(Role).all():
        if r.role_name.lower().strip() == name:
            return r
    return None


def _make_teamlead(db, group: LabGroup) -> User:
    role = _role(db, "teamlead")
    if role is None:
        pytest.skip("No 'teamlead' role seeded; run dev_seed.sql.")
    suffix = _next_suffix()
    user = User(
        role_id=role.role_id,
        full_name=f"W11 Test Lead {suffix}",
        email=f"w11t.lead.{suffix}@example.test",
        password_hash="placeholder_no_auth_yet",
        lab_group_id=group.lab_group_id,
    )
    db.add(user)
    db.flush()
    return user


# ─── 1. Calculation test on a known dataset (/spending) ──────────────────
def test_spending_splits_approved_and_pending(db, admin_user):
    """Known dataset: one $300 Approved line + one $200 Pending line in a
    fresh group → that group reports exactly 300 actual / 200 pending."""
    group = _make_group(db)
    lab = _make_lab(db, group)
    cat = _make_category(db)
    _add_line(db, lab, cat, "300.00", "Approved")
    _add_line(db, lab, cat, "200.00", "Pending Approval")

    result = get_spending_summary(db=db, current_user=admin_user)

    key = str(group.lab_group_id)
    assert Decimal(result.by_lab_group[key]) == Decimal("300.00")
    assert Decimal(result.pending_by_lab_group[key]) == Decimal("200.00")


def test_spending_ignores_rejected_and_other_statuses(db, admin_user):
    """Only 'approved%' counts as actual and 'pending%' as pending. A Rejected
    line counts toward neither, so the fresh group shows up in neither bucket."""
    group = _make_group(db)
    lab = _make_lab(db, group)
    cat = _make_category(db)
    _add_line(db, lab, cat, "500.00", "Rejected")

    result = get_spending_summary(db=db, current_user=admin_user)

    key = str(group.lab_group_id)
    assert key not in result.by_lab_group
    assert key not in result.pending_by_lab_group


# ─── 2. Integration test: nested roll-up Lab Group → Lab → Category ──────
def test_breakdown_rolls_up_category_to_lab_to_group(db, admin_user):
    """Two categories under one lab. Lab subtotal must equal the sum of its
    categories, and the group subtotal the sum of its labs. Utilisation and
    projected utilisation computed from the rolled-up budget."""
    group = _make_group(db)
    lab = _make_lab(db, group)
    cat_a = _make_category(db)
    cat_b = _make_category(db)

    # Cat A: budget 1000, approved 300, pending 200
    _set_budget(db, group, lab, cat_a, "1000.00")
    _add_line(db, lab, cat_a, "300.00", "Approved")
    _add_line(db, lab, cat_a, "200.00", "Pending Approval")
    # Cat B: budget 500, approved 100, pending 0
    _set_budget(db, group, lab, cat_b, "500.00")
    _add_line(db, lab, cat_b, "100.00", "Approved (SVP)")

    resp = get_breakdown(db=db, current_user=admin_user)
    grp = next(g for g in resp.lab_groups if g.lab_group_id == group.lab_group_id)

    # Group-level roll-up: budget 1500, approved 400, pending 200
    assert Decimal(grp.budget_sgd) == Decimal("1500.00")
    assert Decimal(grp.actual_spend_sgd) == Decimal("400.00")
    assert Decimal(grp.pending_sgd) == Decimal("200.00")
    assert Decimal(grp.available_balance_sgd) == Decimal("900.00")  # 1500-400-200
    assert grp.utilisation_pct == 26.7  # 400/1500
    assert grp.projected_utilisation_pct == 40.0  # (400+200)/1500

    # Exactly one lab, which mirrors the group totals
    assert len(grp.labs) == 1
    lab_row = grp.labs[0]
    assert Decimal(lab_row.budget_sgd) == Decimal("1500.00")
    assert Decimal(lab_row.actual_spend_sgd) == Decimal("400.00")

    # Two category rows summing to the lab
    cats = {c.category_id: c for c in lab_row.categories}
    assert Decimal(cats[cat_a.category_id].actual_spend_sgd) == Decimal("300.00")
    assert Decimal(cats[cat_a.category_id].available_balance_sgd) == Decimal("500.00")
    assert Decimal(cats[cat_b.category_id].actual_spend_sgd) == Decimal("100.00")
    assert cats[cat_b.category_id].utilisation_pct == 20.0  # 100/500


# ─── 3. Boundary tests ───────────────────────────────────────────────────
def test_zero_budget_does_not_divide_by_zero(db, admin_user):
    """A cell with spending but no (or zero) budget must yield 0% utilisation
    rather than raising — and available balance goes negative as expected."""
    group = _make_group(db)
    lab = _make_lab(db, group)
    cat = _make_category(db)
    # No budget row at all, just an approved spend of 100.
    _add_line(db, lab, cat, "100.00", "Approved")

    resp = get_breakdown(db=db, current_user=admin_user)
    grp = next(g for g in resp.lab_groups if g.lab_group_id == group.lab_group_id)

    assert Decimal(grp.budget_sgd) == Decimal("0")
    assert grp.utilisation_pct == 0.0
    assert grp.projected_utilisation_pct == 0.0
    assert Decimal(grp.available_balance_sgd) == Decimal("-100.00")


def test_missing_category_line_is_handled(db, admin_user):
    """A committed line whose category could not be resolved (category_id NULL)
    must still aggregate without crashing the breakdown."""
    group = _make_group(db)
    lab = _make_lab(db, group)
    _add_line(db, lab, None, "150.00", "Approved")

    resp = get_breakdown(db=db, current_user=admin_user)
    grp = next(g for g in resp.lab_groups if g.lab_group_id == group.lab_group_id)

    assert Decimal(grp.actual_spend_sgd) == Decimal("150.00")


# ─── 4. Locked spec rule: General lab group excluded ─────────────────────
def test_general_lab_group_excluded_from_totals(db, admin_user):
    """Lines under a lab group literally named 'General' are unresolved review
    items and must NOT count toward any totals (spec rule #4)."""
    general = _make_group(db, name="General")
    lab = _make_lab(db, general)
    cat = _make_category(db)
    _add_line(db, lab, cat, "777.00", "Approved")

    spending = get_spending_summary(db=db, current_user=admin_user)
    assert str(general.lab_group_id) not in spending.by_lab_group

    breakdown = get_breakdown(db=db, current_user=admin_user)
    assert all(g.lab_group_id != general.lab_group_id for g in breakdown.lab_groups)


# ─── 5. Role scoping ─────────────────────────────────────────────────────
def test_lab_ic_forbidden(db):
    """Lab IC is blocked from the dashboard aggregates (403)."""
    labic = db.query(User).filter(User.email == "labic@test.com").first()
    if labic is None:
        pytest.skip("Seed labic@test.com missing; run dev_seed.sql.")

    with pytest.raises(HTTPException) as exc:
        get_spending_summary(db=db, current_user=labic)
    assert exc.value.status_code == 403


def test_teamlead_sees_only_own_group(db):
    """A Team Lead scoped to group A sees A's spend but not group B's."""
    group_a = _make_group(db)
    lab_a = _make_lab(db, group_a)
    cat_a = _make_category(db)
    _add_line(db, lab_a, cat_a, "400.00", "Approved")

    group_b = _make_group(db)
    lab_b = _make_lab(db, group_b)
    cat_b = _make_category(db)
    _add_line(db, lab_b, cat_b, "999.00", "Approved")

    lead = _make_teamlead(db, group_a)
    result = get_spending_summary(db=db, current_user=lead)

    assert str(group_a.lab_group_id) in result.by_lab_group
    assert Decimal(result.by_lab_group[str(group_a.lab_group_id)]) == Decimal("400.00")
    assert str(group_b.lab_group_id) not in result.by_lab_group
