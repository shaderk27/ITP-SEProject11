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


_LLM_ENV = (
    "LLM_API_KEY",
    "LLM_BASE_URL",
    "LLM_MODEL",
    "OPENROUTER_API_KEY",
    "OPENROUTER_MODEL",
)


@pytest.fixture
def llm_env(monkeypatch):
    """Clear every LLM setting (the real .env may have some), then set only ours."""
    for name in _LLM_ENV:
        monkeypatch.setenv(name, "")

    def _set(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name, value)

    return _set


class _FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body
        self.text = str(body)

    def json(self) -> dict:
        return self._body


def _ok(text: str = "ok") -> _FakeResponse:
    return _FakeResponse(200, {"choices": [{"message": {"content": text}}]})


@pytest.fixture
def fake_post(monkeypatch):
    """Record every outgoing request and answer from a queue of responses."""
    calls: list[dict] = []
    queue: list[_FakeResponse] = []

    def _post(url, headers, json, timeout):
        calls.append({"url": url, "headers": headers, "json": dict(json)})
        return queue.pop(0) if queue else _ok()

    monkeypatch.setattr(llm_client.httpx, "post", _post)
    return calls, queue


def test_generate_answer_without_key_raises_unavailable(llm_env):
    with pytest.raises(llm_client.LLMUnavailableError):
        llm_client.generate_answer([{"role": "user", "content": "hi"}])


def test_defaults_to_openrouter(llm_env, fake_post):
    calls, _ = fake_post
    llm_env(LLM_API_KEY="sk-or-test")

    assert llm_client.generate_answer([{"role": "user", "content": "hi"}]) == "ok"
    assert calls[0]["url"] == "https://openrouter.ai/api/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-or-test"
    assert "X-OpenRouter-Title" in calls[0]["headers"]
    assert calls[0]["json"]["model"] == llm_client.DEFAULT_MODEL


def test_old_openrouter_env_names_still_work(llm_env, fake_post):
    calls, _ = fake_post
    llm_env(OPENROUTER_API_KEY="sk-or-legacy", OPENROUTER_MODEL="openai/gpt-4o-mini")

    assert llm_client.llm_configured()
    llm_client.generate_answer([{"role": "user", "content": "hi"}])
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-or-legacy"
    assert calls[0]["json"]["model"] == "openai/gpt-4o-mini"


def test_switching_to_openai_is_env_only(llm_env, fake_post):
    calls, _ = fake_post
    llm_env(
        LLM_API_KEY="sk-proj-test",
        LLM_BASE_URL="https://api.openai.com/v1/",
        LLM_MODEL="gpt-4o-mini",
    )

    llm_client.generate_answer([{"role": "user", "content": "hi"}])
    assert calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-proj-test"
    assert "X-OpenRouter-Title" not in calls[0]["headers"]
    assert calls[0]["json"]["model"] == "gpt-4o-mini"


def test_new_env_names_win_over_old_ones(llm_env, fake_post):
    calls, _ = fake_post
    llm_env(OPENROUTER_API_KEY="sk-or-old", LLM_API_KEY="sk-new")

    llm_client.generate_answer([{"role": "user", "content": "hi"}])
    assert calls[0]["headers"]["Authorization"] == "Bearer sk-new"


def test_retries_without_temperature_when_model_rejects_it(llm_env, fake_post):
    calls, queue = fake_post
    llm_env(LLM_API_KEY="k", LLM_BASE_URL="https://api.openai.com/v1")
    queue.extend(
        [
            _FakeResponse(
                400,
                {
                    "error": {
                        "message": "Unsupported value: 'temperature'",
                        "param": "temperature",
                    }
                },
            ),
            _ok("second try"),
        ]
    )

    assert (
        llm_client.generate_answer([{"role": "user", "content": "hi"}]) == "second try"
    )
    assert "temperature" in calls[0]["json"]
    assert "temperature" not in calls[1]["json"]


def test_other_errors_are_not_retried(llm_env, fake_post):
    calls, queue = fake_post
    llm_env(LLM_API_KEY="bad")
    queue.append(_FakeResponse(401, {"error": {"message": "Invalid API key"}}))

    with pytest.raises(llm_client.LLMUnavailableError, match="401"):
        llm_client.generate_answer([{"role": "user", "content": "hi"}])
    assert len(calls) == 1


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
