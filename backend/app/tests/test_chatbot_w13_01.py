from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

import pytest

from app.api.dashboard import get_breakdown
from app.models.auth import Role, User
from app.models.config import (
    Budget,
    BudgetPeriod,
    Lab,
    LabGroup,
    LabIcAssignment,
    SpendingCategory,
)
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.schemas.chatbot_schema import ChatbotContextRequest
from app.services.chatbot_service import (
    build_chatbot_context,
    supported_chatbot_questions,
)

_SEQ = {"n": 0}


def _next_suffix() -> str:
    _SEQ["n"] += 1
    return f"{_SEQ['n']:04d}"


def _role(db, name: str) -> Role | None:
    for role in db.query(Role).all():
        if role.role_name.lower().strip() == name:
            return role
    return None


def _seeded_group_lab_pairs(db, count: int = 1) -> list[tuple[LabGroup, Lab]]:
    pairs: list[tuple[LabGroup, Lab]] = []
    groups = (
        db.query(LabGroup)
        .filter(LabGroup.lab_group_name != "General")
        .order_by(LabGroup.lab_group_id)
        .all()
    )
    for group in groups:
        lab = (
            db.query(Lab)
            .filter(Lab.lab_group_id == group.lab_group_id)
            .order_by(Lab.lab_id)
            .first()
        )
        if lab is not None:
            pairs.append((group, lab))
        if len(pairs) >= count:
            return pairs
    pytest.skip(f"Need at least {count} seeded non-General lab group/lab pair(s).")


def _make_category(db) -> SpendingCategory:
    suffix = _next_suffix()
    category = SpendingCategory(category_name=f"W13 Chat Cat {suffix}")
    db.add(category)
    db.flush()
    return category


def _seeded_period_id(db) -> int:
    period = db.query(BudgetPeriod).order_by(BudgetPeriod.period_id).first()
    if period is None:
        pytest.skip("No budget periods seeded; run backend/seeds/dev_seed.sql.")
    return period.period_id


def _set_budget(
    db,
    group: LabGroup,
    lab: Lab,
    category: SpendingCategory,
    amount: str,
    period_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        Budget(
            period_id=period_id,
            lab_group_id=group.lab_group_id,
            lab_id=lab.lab_id,
            category_id=category.category_id,
            budget_amount=Decimal(amount),
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()


def _set_group_envelope(
    db,
    group: LabGroup,
    amount: str,
    period_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    db.add(
        Budget(
            period_id=period_id,
            lab_group_id=group.lab_group_id,
            lab_id=None,
            category_id=None,
            budget_amount=Decimal(amount),
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()


def _add_line(
    db,
    group: LabGroup,
    lab: Lab,
    category: SpendingCategory,
    amount: str,
    pr_status: str,
    request_date: date = date(2042, 5, 1),
) -> None:
    suffix = _next_suffix()
    pr = PurchaseRequest(
        source_pr_number=f"PR-W13-{suffix}",
        requestor_name="W13 Requestor",
        request_date=request_date,
        purpose="W13 chatbot context test",
        wbs_code=group.wbs_code,
        grand_total_sgd=Decimal(amount),
        lab_group_id=group.lab_group_id,
        pr_status=pr_status,
    )
    db.add(pr)
    db.flush()
    db.add(
        PurchaseRequestLine(
            pr_id=pr.pr_id,
            line_no=1,
            item_description=f"W13 approved line {suffix}",
            amount_gst=Decimal(amount),
            currency_code="SGD",
            lab_id=lab.lab_id,
            category_id=category.category_id,
            pr_status=pr_status,
        )
    )
    db.flush()


def _make_teamlead(db, group: LabGroup) -> User:
    role = _role(db, "teamlead")
    if role is None:
        pytest.skip("No teamlead role seeded; run backend/seeds/dev_seed.sql.")
    suffix = _next_suffix()
    user = User(
        role_id=role.role_id,
        full_name=f"W13 Lead {suffix}",
        email=f"w13.lead.{suffix}@example.test",
        password_hash="placeholder",
        lab_group_id=group.lab_group_id,
    )
    db.add(user)
    db.flush()
    return user


def _make_labic(db, lab: Lab) -> User:
    role = _role(db, "labic")
    if role is None:
        pytest.skip("No labic role seeded; run backend/seeds/dev_seed.sql.")
    suffix = _next_suffix()
    user = User(
        role_id=role.role_id,
        full_name=f"W13 IC {suffix}",
        email=f"w13.ic.{suffix}@example.test",
        password_hash="placeholder",
    )
    db.add(user)
    db.flush()
    db.add(LabIcAssignment(lab_id=lab.lab_id, user_id=user.user_id, is_primary=True))
    db.flush()
    db.refresh(user)
    return user


def test_supported_questions_publish_w13_01_query_types():
    response = supported_chatbot_questions()
    query_types = {item.query_type for item in response.supported_query_types}

    assert "budget_utilisation_summary" in query_types
    assert "high_spending_areas" in query_types
    assert "budget_risks" in query_types
    assert "spending_trends" in query_types
    assert "purchase_lookup" in query_types
    assert "purchase_request_lines" in response.data_sources


def test_chatbot_context_uses_approved_purchase_data_only(db, admin_user):
    group, lab = _seeded_group_lab_pairs(db)[0]
    category = _make_category(db)
    period_id = _seeded_period_id(db)
    request = ChatbotContextRequest(
        query_type="budget_utilisation_summary",
        period_id=period_id,
        date_range="all",
    )
    before = build_chatbot_context(db, admin_user, request)
    before_group = next(
        (
            item
            for item in before.lab_group_budget_context
            if item.lab_group_id == group.lab_group_id
        ),
        None,
    )
    baseline_envelope = Decimal(before_group.envelope_budget_sgd) if before_group else 0
    baseline_allocated = (
        Decimal(before_group.allocated_to_labs_sgd) if before_group else 0
    )
    baseline_unallocated = Decimal(before_group.unallocated_sgd) if before_group else 0
    baseline_approved = Decimal(before_group.approved_spend_sgd) if before_group else 0
    baseline_pending = Decimal(before_group.pending_spend_sgd) if before_group else 0

    _set_group_envelope(db, group, "5000.00", period_id)
    _set_budget(db, group, lab, category, "1000.00", period_id)
    _add_line(db, group, lab, category, "250.00", "Approved")
    _add_line(db, group, lab, category, "999.00", "Pending Approval")

    response = build_chatbot_context(db, admin_user, request)
    row = next(
        item
        for item in response.budget_context
        if item.lab_id == lab.lab_id and item.category_id == category.category_id
    )

    assert Decimal(row.budget_sgd) == Decimal("1000.00")
    assert Decimal(row.approved_spend_sgd) == Decimal("250.00")
    assert Decimal(row.pending_spend_sgd) == Decimal("999.00")
    assert Decimal(row.projected_spend_sgd) == Decimal("1249.00")
    assert Decimal(row.remaining_after_pending_sgd) == Decimal("-249.00")
    group_row = next(
        item
        for item in response.lab_group_budget_context
        if item.lab_group_id == group.lab_group_id
    )
    assert Decimal(group_row.envelope_budget_sgd) - baseline_envelope == Decimal(
        "5000.00"
    )
    assert Decimal(group_row.allocated_to_labs_sgd) - baseline_allocated == Decimal(
        "1000.00"
    )
    assert Decimal(group_row.unallocated_sgd) - baseline_unallocated == Decimal(
        "4000.00"
    )
    assert Decimal(group_row.approved_spend_sgd) - baseline_approved == Decimal(
        "250.00"
    )
    assert Decimal(group_row.pending_spend_sgd) - baseline_pending == Decimal("999.00")
    visible_amounts = {Decimal(line.amount_gst) for line in response.purchase_lines}
    assert Decimal("250.00") in visible_amounts
    assert Decimal("999.00") not in visible_amounts


def test_chatbot_figures_reconcile_with_dashboard_and_report_source(db, admin_user):
    group, lab = _seeded_group_lab_pairs(db)[0]
    category = _make_category(db)
    period = db.query(BudgetPeriod).order_by(BudgetPeriod.period_id).first()
    if period is None:
        pytest.skip("No budget periods seeded; run backend/seeds/dev_seed.sql.")
    start = period.start_date or date(period.year_no, 4, 1)
    end = period.end_date or date(period.year_no + 1, 3, 31)

    _set_budget(db, group, lab, category, "1000.00", period.period_id)
    _add_line(db, group, lab, category, "320.00", "Approved", start)
    _add_line(db, group, lab, category, "80.00", "Pending Approval", start)

    chatbot = build_chatbot_context(
        db,
        admin_user,
        ChatbotContextRequest(
            query_type="budget_utilisation_summary",
            period_id=period.period_id,
            start_date=start,
            end_date=end,
        ),
    )
    chatbot_row = next(
        row
        for row in chatbot.budget_context
        if row.lab_id == lab.lab_id and row.category_id == category.category_id
    )

    dashboard = get_breakdown(
        date_range="all",
        start_date=start,
        end_date=end,
        period_id=period.period_id,
        db=db,
        current_user=admin_user,
    )
    dashboard_row = next(
        category_row
        for group_row in dashboard.lab_groups
        for lab_row in group_row.labs
        for category_row in lab_row.categories
        if lab_row.lab_id == lab.lab_id
        and category_row.category_id == category.category_id
    )

    assert Decimal(chatbot_row.budget_sgd) == Decimal(dashboard_row.budget_sgd)
    assert Decimal(chatbot_row.approved_spend_sgd) == Decimal(
        dashboard_row.actual_spend_sgd
    )
    assert Decimal(chatbot_row.pending_spend_sgd) == Decimal(dashboard_row.pending_sgd)
    assert Decimal(chatbot_row.remaining_after_pending_sgd) == Decimal(
        dashboard_row.available_balance_sgd
    )
    assert chatbot_row.utilisation_pct == dashboard_row.utilisation_pct
    assert (
        chatbot_row.projected_utilisation_pct == dashboard_row.projected_utilisation_pct
    )


def test_chatbot_context_scopes_teamlead_to_own_lab_group(db):
    (group_a, lab_a), (group_b, lab_b) = _seeded_group_lab_pairs(db, count=2)
    category_a = _make_category(db)
    category_b = _make_category(db)
    period_id = _seeded_period_id(db)
    _set_budget(db, group_a, lab_a, category_a, "1000.00", period_id)
    _set_budget(db, group_b, lab_b, category_b, "1000.00", period_id)
    _add_line(db, group_a, lab_a, category_a, "100.00", "Approved")
    _add_line(db, group_b, lab_b, category_b, "900.00", "Approved")
    lead = _make_teamlead(db, group_a)

    response = build_chatbot_context(
        db,
        lead,
        ChatbotContextRequest(query_type="purchase_lookup", period_id=period_id),
    )

    assert {row.lab_group_id for row in response.budget_context} == {
        group_a.lab_group_id
    }
    assert {line.lab_group_name for line in response.purchase_lines} == {
        group_a.lab_group_name
    }


def test_chatbot_context_scopes_lab_ic_to_own_lab(db):
    group, lab_a = _seeded_group_lab_pairs(db)[0]
    lab_b = (
        db.query(Lab)
        .filter(Lab.lab_group_id == group.lab_group_id)
        .filter(Lab.lab_id != lab_a.lab_id)
        .order_by(Lab.lab_id)
        .first()
    )
    if lab_b is None:
        pytest.skip("Need at least two seeded labs in one non-General lab group.")
    category = _make_category(db)
    period_id = _seeded_period_id(db)
    _set_budget(db, group, lab_a, category, "1000.00", period_id)
    _set_budget(db, group, lab_b, category, "2000.00", period_id)
    _add_line(db, group, lab_a, category, "100.00", "Approved")
    _add_line(db, group, lab_b, category, "900.00", "Approved")
    labic = _make_labic(db, lab_a)

    response = build_chatbot_context(
        db,
        labic,
        ChatbotContextRequest(query_type="purchase_lookup", period_id=period_id),
    )

    assert {row.lab_id for row in response.budget_context} == {lab_a.lab_id}
    assert response.lab_group_budget_context == []
    assert {line.lab_name for line in response.purchase_lines} == {lab_a.lab_name}


def test_unsupported_chatbot_query_type_fails_before_retrieval(db, admin_user):
    with pytest.raises(ValueError, match="Unsupported chatbot query type"):
        build_chatbot_context(
            db,
            admin_user,
            ChatbotContextRequest(query_type="unsupported_query"),
        )
