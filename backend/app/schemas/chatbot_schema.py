from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

SUPPORTED_CHATBOT_QUERY_TYPES = [
    "budget_utilisation_summary",
    "high_spending_areas",
    "budget_risks",
    "spending_trends",
    "purchase_lookup",
]


class SupportedChatbotQuestion(BaseModel):
    query_type: str
    label: str
    description: str
    example_questions: list[str]


class SupportedChatbotQuestionsResponse(BaseModel):
    supported_query_types: list[SupportedChatbotQuestion]
    data_sources: list[str]
    guardrails: list[str]


class ChatbotContextRequest(BaseModel):
    query_type: str = Field(
        ...,
        description="One of the supported chatbot query type identifiers.",
    )
    question: str | None = Field(
        default=None,
        description="Optional natural language question for audit/debug context.",
    )
    date_range: Literal["all", "fy", "7d", "30d", "90d", "ytd"] = "all"
    start_date: date | None = None
    end_date: date | None = None
    period_id: int | None = None
    limit: int = Field(default=10, ge=1, le=50)


class ChatbotScope(BaseModel):
    role: str
    lab_group_id: int | None
    lab_ids: list[int] = []
    scope_description: str


class ChatbotBudgetContext(BaseModel):
    lab_group_id: int
    lab_group_name: str
    lab_id: int
    lab_name: str
    category_id: int | None
    category_name: str
    budget_sgd: str
    approved_spend_sgd: str
    remaining_sgd: str
    utilisation_pct: float
    pending_spend_sgd: str = "0"
    projected_spend_sgd: str = "0"
    remaining_after_pending_sgd: str = "0"
    projected_utilisation_pct: float | None = None


class ChatbotLabGroupBudgetContext(BaseModel):
    lab_group_id: int
    lab_group_name: str
    envelope_budget_sgd: str
    allocated_to_labs_sgd: str
    unallocated_sgd: str
    approved_spend_sgd: str
    utilisation_pct: float
    pending_spend_sgd: str = "0"
    projected_spend_sgd: str = "0"
    remaining_after_pending_sgd: str = "0"
    projected_utilisation_pct: float | None = None


class ChatbotPurchaseLineContext(BaseModel):
    pr_id: int
    pr_line_id: int
    source_pr_number: str
    request_date: str | None
    requestor_name: str
    purpose: str
    wbs_code: str
    item_description: str
    amount_gst: str
    currency_code: str
    lab_group_name: str
    lab_name: str
    category_name: str
    pr_status: str | None


class ChatbotContextResponse(BaseModel):
    query_type: str
    question: str | None
    scope: ChatbotScope
    data_sources: list[str]
    supported_query_types: list[str]
    lab_group_budget_context: list[ChatbotLabGroupBudgetContext]
    budget_context: list[ChatbotBudgetContext]
    purchase_lines: list[ChatbotPurchaseLineContext]
    notes: list[str]


class ChatbotHistoryTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(..., max_length=4000)


class ChatbotAskRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)
    history: list[ChatbotHistoryTurn] = Field(
        default_factory=list,
        description="Earlier turns of this chat, oldest first, for follow-up questions.",
    )
    # Page context (W15-03): the Dashboard's Fiscal Year + effective date
    # window, so answers match what the user is looking at. All omitted means
    # the current fiscal year.
    period_id: int | None = Field(
        default=None,
        description="Dashboard Fiscal Year filter; 0 = all fiscal years.",
    )
    start_date: date | None = None
    end_date: date | None = None


class ChatbotAnswerSource(BaseModel):
    """Evidence behind an answer (W13-03A), shown under it in the widget."""

    type: Literal["sql_calculation", "pr_line", "document", "audit_event"]
    ref: str = Field(..., description='Citation label, e.g. "PR 4500012345 line 2".')
    detail: str


class ChatbotAskResponse(BaseModel):
    answer: str
    scope: ChatbotScope
    model: str
    period_label: str
    record_counts: dict[str, int]
    focus: list[str]
    notes: list[str]
    sources: list[ChatbotAnswerSource] = Field(default_factory=list)
    # True when the question was outside what Ask AI answers; `answer` is then
    # the fixed "what you can ask" message.
    out_of_scope: bool = False
