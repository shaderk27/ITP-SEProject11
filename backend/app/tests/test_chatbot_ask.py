"""Ask AI answer flow: fact sheet shaping and LLM fallback. No DB, no network."""

from __future__ import annotations

import pytest

from app.schemas.chatbot_schema import (
    ChatbotAskRequest,
    ChatbotBudgetContext,
    ChatbotContextResponse,
    ChatbotScope,
)
from app.services import chatbot_answer_service, llm_client
from app.services.chatbot_answer_service import _build_facts


def _row(group, lab, category, budget, spend) -> ChatbotBudgetContext:
    return ChatbotBudgetContext(
        lab_group_id=1,
        lab_group_name=group,
        lab_id=hash(lab) % 1000,
        lab_name=lab,
        category_id=hash(category) % 1000,
        category_name=category,
        budget_sgd=str(budget),
        approved_spend_sgd=str(spend),
        remaining_sgd=str(budget - spend),
        utilisation_pct=0.0,
    )


def _context(role: str, rows: list[ChatbotBudgetContext]) -> ChatbotContextResponse:
    return ChatbotContextResponse(
        query_type="budget_utilisation_summary",
        question=None,
        scope=ChatbotScope(
            role=role, lab_group_id=None, lab_id=None, scope_description=""
        ),
        data_sources=[],
        supported_query_types=[],
        lab_group_budget_context=[],
        budget_context=rows,
        purchase_lines=[],
        notes=[],
    )


FCB_ROWS = [
    _row("FCB", "Food Lab", "Chemicals", 1000, 900),
    _row("FCB", "Food Lab", "Tools", 1000, 1200),
    _row("FCB", "Brew Lab", "Chemicals", 1000, 100),
]


def test_facts_precompute_totals_and_risk_counts():
    facts = _build_facts(_context("teamlead", FCB_ROWS), "overview", "FY")

    assert facts["overall"]["budget"] == 3000.0
    assert facts["overall"]["approved_spend"] == 2200.0
    assert facts["overall"]["over_budget_lines"] == 1
    assert facts["overall"]["at_risk_lines"] == 2
    food = next(lab for lab in facts["labs"] if lab["name"] == "Food Lab")
    assert food["utilisation_pct"] == 105.0


def test_no_budget_means_null_utilisation_not_zero():
    rows = [_row("FCB", "Food Lab", "Tools", 0, 500)]
    facts = _build_facts(_context("teamlead", rows), "x", "FY")

    assert facts["overall"]["utilisation_pct"] is None
    assert facts["overall"]["over_budget_lines"] == 1


def test_focus_only_matches_names_in_scope():
    facts = _build_facts(_context("teamlead", FCB_ROWS), "How is ICT vs FCB?", "FY")

    assert facts["focus"]["matched"] == ["FCB"]
    labs = facts["focus"]["lab_group: FCB"]["labs_by_utilisation"]
    assert [lab["name"] for lab in labs] == ["Food Lab", "Brew Lab"]


def test_lab_ic_gets_no_lab_group_summary():
    rows = [_row("ICT", "Embedded Lab", "Tools", 1000, 100)]
    facts = _build_facts(_context("labic", rows), "x", "FY")

    assert "lab_groups" not in facts


def test_generate_answer_without_key_raises_unavailable(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "")

    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client.generate_answer([{"role": "user", "content": "hi"}])


def test_answer_question_sends_scoped_facts_to_llm(monkeypatch):
    captured = {}

    def fake_context(db, user, request):
        return _context("teamlead", FCB_ROWS)

    def fake_generate(messages, temperature=0.2):
        captured["messages"] = messages
        return "FCB has spent S$2,200.00."

    monkeypatch.setattr(chatbot_answer_service, "build_chatbot_context", fake_context)
    monkeypatch.setattr(llm_client, "generate_answer", fake_generate)

    response = chatbot_answer_service.answer_question(
        None, None, ChatbotAskRequest(question="Total spend?")
    )

    assert response.answer == "FCB has spent S$2,200.00."
    assert response.record_counts["budget_lines"] == 3
    system, user = captured["messages"][0], captured["messages"][-1]
    assert "Team Lead" in system["content"] and "FCB" in system["content"]
    assert user == {"role": "user", "content": "Total spend?"}
