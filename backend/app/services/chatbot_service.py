from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from sqlalchemy import case, func
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.schemas.chatbot_schema import (
    SUPPORTED_CHATBOT_QUERY_TYPES,
    ChatbotBudgetContext,
    ChatbotContextRequest,
    ChatbotContextResponse,
    ChatbotLabGroupBudgetContext,
    ChatbotPurchaseLineContext,
    ChatbotScope,
    SupportedChatbotQuestion,
    SupportedChatbotQuestionsResponse,
)
from app.utils.date_range import date_range_bounds

CHATBOT_ALLOWED_ROLES = {"admin", "teamlead", "labic"}


def supported_chatbot_questions() -> SupportedChatbotQuestionsResponse:
    return SupportedChatbotQuestionsResponse(
        supported_query_types=[
            SupportedChatbotQuestion(
                query_type="budget_utilisation_summary",
                label="Budget utilisation summary",
                description="Summarise approved spend, budget, remaining balance, and utilisation by authorised lab scope.",
                example_questions=[
                    "What is my current budget utilisation?",
                    "Summarise approved spending for my lab group.",
                ],
            ),
            SupportedChatbotQuestion(
                query_type="high_spending_areas",
                label="High-spending areas",
                description="Find labs or categories with the highest approved spend in the user's permitted scope.",
                example_questions=[
                    "Which categories are spending the most?",
                    "Show the top spending labs this fiscal year.",
                ],
            ),
            SupportedChatbotQuestion(
                query_type="budget_risks",
                label="Budget risks",
                description="Highlight budget rows with high utilisation or negative remaining balance.",
                example_questions=[
                    "Which budgets are at risk?",
                    "Any categories close to exceeding budget?",
                ],
            ),
            SupportedChatbotQuestion(
                query_type="spending_trends",
                label="Spending trends",
                description="Retrieve approved purchase data that later chatbot stages can group into time-based trends.",
                example_questions=[
                    "How has spending changed over time?",
                    "Show recent approved purchases.",
                ],
            ),
            SupportedChatbotQuestion(
                query_type="purchase_lookup",
                label="Purchase lookup",
                description="Look up approved purchase lines by PR details, lab, category, requester, or WBS within authorised scope.",
                example_questions=[
                    "Show approved purchases for this WBS.",
                    "What purchases did this lab make?",
                ],
            ),
        ],
        data_sources=[
            "purchase_requests",
            "purchase_request_lines",
            "budgets",
            "lab_groups",
            "labs",
            "spending_categories",
        ],
        guardrails=[
            "Only approved purchase lines are exposed as actual spend.",
            "Responses are scoped by the caller's role, lab group, and lab assignment.",
            "General/unknown lab groups are excluded from budget context until reviewed.",
            "Unsupported query types are rejected before any data is retrieved.",
        ],
    )


def build_chatbot_context(
    db: Session,
    current_user: User,
    request: ChatbotContextRequest,
) -> ChatbotContextResponse:
    role_name = _role_name(current_user)
    if request.query_type not in SUPPORTED_CHATBOT_QUERY_TYPES:
        raise ValueError("Unsupported chatbot query type.")
    if role_name not in CHATBOT_ALLOWED_ROLES:
        raise PermissionError("This role cannot use the chatbot.")
    if role_name == "teamlead" and not current_user.lab_group_id:
        return _empty_response(
            request, current_user, "Team Lead has no assigned Lab Group."
        )
    if role_name == "labic" and not current_user.lab_ids:
        return _empty_response(request, current_user, "Lab IC has no assigned Lab.")

    start, end = _resolve_bounds(request)
    lab_group_budget_context = _lab_group_budget_context(
        db, current_user, request.period_id, start, end
    )
    budget_context = _budget_context(db, current_user, request.period_id, start, end)
    purchase_lines = _purchase_line_context(db, current_user, start, end, request.limit)

    return ChatbotContextResponse(
        query_type=request.query_type,
        question=request.question,
        scope=_scope(current_user),
        data_sources=[
            "purchase_requests",
            "purchase_request_lines",
            "budgets",
            "lab_groups",
            "labs",
            "spending_categories",
        ],
        supported_query_types=SUPPORTED_CHATBOT_QUERY_TYPES,
        lab_group_budget_context=lab_group_budget_context,
        budget_context=budget_context,
        purchase_lines=purchase_lines,
        notes=[
            "This endpoint returns authorised structured context only; natural-language answer generation is handled by later chatbot tasks.",
            "Approved spend uses PR line statuses that start with 'approved'.",
        ],
    )


def _lab_group_budget_context(
    db: Session,
    current_user: User,
    period_id: int | None,
    start: date | None,
    end: date | None,
) -> list[ChatbotLabGroupBudgetContext]:
    role_name = _role_name(current_user)
    if role_name == "labic":
        return []

    budget_period = _resolve_period_id(db, period_id)

    envelope_query = (
        db.query(
            Budget.lab_group_id,
            func.coalesce(func.sum(Budget.budget_amount), 0),
        )
        .join(LabGroup, LabGroup.lab_group_id == Budget.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .filter(Budget.lab_id.is_(None))
        .group_by(Budget.lab_group_id)
    )
    allocation_query = (
        db.query(
            Budget.lab_group_id,
            func.coalesce(func.sum(Budget.budget_amount), 0),
        )
        .join(LabGroup, LabGroup.lab_group_id == Budget.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .filter(Budget.lab_id.isnot(None))
        .group_by(Budget.lab_group_id)
    )
    if budget_period is not None:
        envelope_query = envelope_query.filter(Budget.period_id == budget_period)
        allocation_query = allocation_query.filter(Budget.period_id == budget_period)
    if role_name == "teamlead":
        envelope_query = envelope_query.filter(
            Budget.lab_group_id == current_user.lab_group_id
        )
        allocation_query = allocation_query.filter(
            Budget.lab_group_id == current_user.lab_group_id
        )

    envelopes = {
        int(group_id): _to_decimal(amount)
        for group_id, amount in envelope_query.all()
        if group_id is not None
    }
    allocations = {
        int(group_id): _to_decimal(amount)
        for group_id, amount in allocation_query.all()
        if group_id is not None
    }

    spend_query = (
        db.query(
            Lab.lab_group_id,
            func.coalesce(
                func.sum(
                    case(
                        (
                            PurchaseRequestLine.pr_status.ilike("approved%"),
                            PurchaseRequestLine.amount_gst,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .group_by(Lab.lab_group_id)
    )
    spend_query = _apply_date_bounds(spend_query, start, end)
    spend_query = _apply_role_scope(spend_query, current_user)

    spends = {
        int(group_id): _to_decimal(amount)
        for group_id, amount in spend_query.all()
        if group_id is not None
    }
    group_names = {g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()}

    rows: list[ChatbotLabGroupBudgetContext] = []
    for group_id in sorted(set(envelopes) | set(allocations) | set(spends)):
        envelope = envelopes.get(group_id, Decimal("0"))
        allocated = allocations.get(group_id, Decimal("0"))
        spend = spends.get(group_id, Decimal("0"))
        rows.append(
            ChatbotLabGroupBudgetContext(
                lab_group_id=group_id,
                lab_group_name=group_names.get(group_id, "Unknown"),
                envelope_budget_sgd=str(envelope),
                allocated_to_labs_sgd=str(allocated),
                unallocated_sgd=str(envelope - allocated),
                approved_spend_sgd=str(spend),
                utilisation_pct=_pct(spend, envelope),
            )
        )
    return rows


def _budget_context(
    db: Session,
    current_user: User,
    period_id: int | None,
    start: date | None,
    end: date | None,
) -> list[ChatbotBudgetContext]:
    role_name = _role_name(current_user)
    budget_period = _resolve_period_id(db, period_id)

    budget_query = (
        db.query(
            Budget.lab_group_id,
            Budget.lab_id,
            Budget.category_id,
            func.coalesce(func.sum(Budget.budget_amount), 0),
        )
        .join(LabGroup, LabGroup.lab_group_id == Budget.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .group_by(Budget.lab_group_id, Budget.lab_id, Budget.category_id)
    )
    if budget_period is not None:
        budget_query = budget_query.filter(Budget.period_id == budget_period)
    if role_name == "teamlead":
        budget_query = budget_query.filter(
            Budget.lab_group_id == current_user.lab_group_id
        )
    elif role_name == "labic":
        budget_query = budget_query.filter(Budget.lab_id.in_(current_user.lab_ids))

    budgets: dict[tuple[int, int, int | None], Decimal] = {}
    for group_id, lab_id, category_id, amount in budget_query.all():
        if group_id is None or lab_id is None:
            continue
        budgets[
            (
                int(group_id),
                int(lab_id),
                int(category_id) if category_id is not None else None,
            )
        ] = _to_decimal(amount)

    spend_query = (
        db.query(
            Lab.lab_group_id,
            PurchaseRequestLine.lab_id,
            PurchaseRequestLine.category_id,
            func.coalesce(
                func.sum(
                    case(
                        (
                            PurchaseRequestLine.pr_status.ilike("approved%"),
                            PurchaseRequestLine.amount_gst,
                        ),
                        else_=0,
                    )
                ),
                0,
            ),
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .group_by(
            Lab.lab_group_id,
            PurchaseRequestLine.lab_id,
            PurchaseRequestLine.category_id,
        )
    )
    spend_query = _apply_date_bounds(spend_query, start, end)
    spend_query = _apply_role_scope(spend_query, current_user)

    spends: dict[tuple[int, int, int | None], Decimal] = {}
    for group_id, lab_id, category_id, amount in spend_query.all():
        if group_id is None or lab_id is None:
            continue
        spends[
            (
                int(group_id),
                int(lab_id),
                int(category_id) if category_id is not None else None,
            )
        ] = _to_decimal(amount)

    group_names = {g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()}
    lab_names = {lab.lab_id: lab.lab_name for lab in db.query(Lab).all()}
    category_names = {
        cat.category_id: cat.category_name for cat in db.query(SpendingCategory).all()
    }

    rows: list[ChatbotBudgetContext] = []
    for group_id, lab_id, category_id in sorted(set(budgets) | set(spends)):
        budget = budgets.get((group_id, lab_id, category_id), Decimal("0"))
        spend = spends.get((group_id, lab_id, category_id), Decimal("0"))
        remaining = budget - spend
        rows.append(
            ChatbotBudgetContext(
                lab_group_id=group_id,
                lab_group_name=group_names.get(group_id, "Unknown"),
                lab_id=lab_id,
                lab_name=lab_names.get(lab_id, "Unknown"),
                category_id=category_id,
                category_name=(
                    "Uncategorised"
                    if category_id is None
                    else category_names.get(category_id, "Unknown")
                ),
                budget_sgd=str(budget),
                approved_spend_sgd=str(spend),
                remaining_sgd=str(remaining),
                utilisation_pct=_pct(spend, budget),
            )
        )
    return rows


def _purchase_line_context(
    db: Session,
    current_user: User,
    start: date | None,
    end: date | None,
    limit: int,
) -> list[ChatbotPurchaseLineContext]:
    query = (
        db.query(PurchaseRequest, PurchaseRequestLine, LabGroup, Lab, SpendingCategory)
        .join(PurchaseRequestLine, PurchaseRequestLine.pr_id == PurchaseRequest.pr_id)
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .outerjoin(
            SpendingCategory,
            SpendingCategory.category_id == PurchaseRequestLine.category_id,
        )
        .filter(PurchaseRequestLine.pr_status.ilike("approved%"))
        .filter(LabGroup.lab_group_name != "General")
        .order_by(
            PurchaseRequest.updated_at.desc(), PurchaseRequestLine.pr_line_id.desc()
        )
    )
    query = _apply_date_bounds(query, start, end)
    query = _apply_role_scope(query, current_user)
    query = query.limit(limit)

    rows: list[ChatbotPurchaseLineContext] = []
    for pr, line, group, lab, category in query.all():
        rows.append(
            ChatbotPurchaseLineContext(
                pr_id=int(pr.pr_id),
                pr_line_id=int(line.pr_line_id),
                source_pr_number=pr.source_pr_number,
                request_date=pr.request_date.isoformat() if pr.request_date else None,
                requestor_name=pr.requestor_name or "",
                purpose=pr.purpose or "",
                wbs_code=pr.wbs_code or "",
                item_description=line.item_description or "",
                amount_gst=str(line.amount_gst or Decimal("0")),
                currency_code=line.currency_code or "SGD",
                lab_group_name=group.lab_group_name,
                lab_name=lab.lab_name,
                category_name=category.category_name if category else "Uncategorised",
                pr_status=line.pr_status,
            )
        )
    return rows


def _resolve_bounds(request: ChatbotContextRequest) -> tuple[date | None, date | None]:
    if request.start_date is not None or request.end_date is not None:
        return request.start_date, request.end_date
    return date_range_bounds(request.date_range)


def _resolve_period_id(db: Session, period_id: int | None) -> int | None:
    if period_id == 0:
        return None
    if period_id is not None:
        return period_id

    today = date.today()
    year = today.year if today.month >= 4 else today.year - 1
    period = db.query(BudgetPeriod).filter(BudgetPeriod.year_no == year).first()
    return period.period_id if period else None


def _apply_date_bounds(query, start: date | None, end: date | None):
    if start is not None:
        query = query.filter(PurchaseRequest.request_date >= start)
    if end is not None:
        query = query.filter(PurchaseRequest.request_date <= end)
    return query


def _apply_role_scope(query, current_user: User):
    role_name = _role_name(current_user)
    if role_name == "teamlead":
        return query.filter(Lab.lab_group_id == current_user.lab_group_id)
    if role_name == "labic":
        return query.filter(PurchaseRequestLine.lab_id.in_(current_user.lab_ids))
    return query


def _empty_response(
    request: ChatbotContextRequest,
    current_user: User,
    note: str,
) -> ChatbotContextResponse:
    return ChatbotContextResponse(
        query_type=request.query_type,
        question=request.question,
        scope=_scope(current_user),
        data_sources=[],
        supported_query_types=SUPPORTED_CHATBOT_QUERY_TYPES,
        lab_group_budget_context=[],
        budget_context=[],
        purchase_lines=[],
        notes=[note],
    )


def _scope(user: User) -> ChatbotScope:
    role_name = _role_name(user)
    if role_name == "admin":
        description = "All configured non-General lab groups and labs."
    elif role_name == "teamlead":
        description = "Assigned Lab Group only."
    elif role_name == "labic":
        description = "Assigned Labs only."
    else:
        description = "No chatbot data scope."
    return ChatbotScope(
        role=role_name,
        lab_group_id=user.lab_group_id,
        lab_ids=user.lab_ids,
        scope_description=description,
    )


def _role_name(user: User) -> str:
    return (user.role.role_name if user.role else "").lower().strip()


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or 0))


def _pct(numerator: Decimal, denominator: Decimal) -> float:
    if denominator <= 0:
        return 0.0
    return round(float((numerator / denominator) * 100), 1)
