"""Ask AI with PR-line evidence (W13-03A): prompt, citations, fallback. No DB, no network."""

from __future__ import annotations

import json
from datetime import date

import pytest
from sqlalchemy.exc import ProgrammingError

from app.schemas.chatbot_schema import (
    ChatbotAskRequest,
    ChatbotBudgetContext,
    ChatbotContextResponse,
    ChatbotScope,
)
from app.services import (
    chatbot_answer_service,
    embedding_client,
    knowledge_service,
    llm_client,
)
from app.services.chatbot_answer_service import _union_window
from app.services.embedding_client import EmbeddingUnavailableError
from app.services.knowledge_service import PRLineHit


def _context() -> ChatbotContextResponse:
    row = ChatbotBudgetContext(
        lab_group_id=1,
        lab_group_name="ICT",
        lab_id=7,
        lab_name="Embedded Lab",
        category_id=3,
        category_name="Equipment",
        budget_sgd="10000",
        approved_spend_sgd="2400",
        remaining_sgd="7600",
        utilisation_pct=24.0,
    )
    return ChatbotContextResponse(
        query_type="budget_utilisation_summary",
        question=None,
        scope=ChatbotScope(
            role="labic", lab_group_id=None, lab_ids=[7], scope_description=""
        ),
        data_sources=[],
        supported_query_types=[],
        lab_group_budget_context=[],
        budget_context=[row],
        purchase_lines=[],
        notes=[],
    )


def _hit(ref: str, item: str) -> PRLineHit:
    return PRLineHit(
        pr_line_id=1,
        source_ref=ref,
        content=f"{ref}\nItem: {item}\nLab: Embedded Lab (E2-02-02), lab group ICT\nStatus: approved",
        distance=0.3,
        lab_id=7,
        lab_name="Embedded Lab",
        lab_group_name="ICT",
        item_description=item,
        pr_status="approved",
        request_date=date(2026, 5, 4),
    )


OSCILLOSCOPE = _hit("PR 4500012345 line 2", "Tektronix oscilloscope")
CHAIRS = _hit("PR 4500099999 line 1", "Office chairs")


class _FakeDb:
    def __init__(self):
        self.rolled_back = False

    def rollback(self):
        self.rolled_back = True


@pytest.fixture
def ask(monkeypatch):
    """Runs answer_question with a fake fact sheet, LLM and search."""
    state: dict = {
        "search_calls": [],
        "answer": "You bought one [PR 4500012345 line 2].",
    }

    monkeypatch.setattr(
        chatbot_answer_service,
        "build_chatbot_context",
        lambda db, user, req: _context(),
    )

    def fake_generate(messages, temperature=0.2):
        state["system"] = messages[0]["content"]
        return state["answer"]

    monkeypatch.setattr(llm_client, "generate_answer", fake_generate)
    monkeypatch.setattr(embedding_client, "embedding_configured", lambda: True)

    def fake_search(db, user, question, limit, start, end, **status_filters):
        state["search_calls"].append(
            {
                "question": question,
                "limit": limit,
                "start": start,
                "end": end,
                **status_filters,
            }
        )
        if "search_error" in state:
            raise state["search_error"]
        return state.get("hits", [OSCILLOSCOPE, CHAIRS])

    monkeypatch.setattr(knowledge_service, "search_pr_lines", fake_search)

    def run(question="Did we buy any oscilloscopes?", db=None, **request_fields):
        state["response"] = chatbot_answer_service.answer_question(
            db, None, ChatbotAskRequest(question=question, **request_fields)
        )
        return state["response"]

    state["run"] = run
    return state


def _facts(system_prompt: str) -> dict:
    return json.loads(system_prompt.split("DATA\n", 1)[1])


def test_matching_purchases_reach_the_prompt_with_source_labels(ask):
    ask["run"]()

    facts = _facts(ask["system"])
    lines = facts["matching_purchases"]["lines"]
    assert [line["source"] for line in lines] == [
        OSCILLOSCOPE.source_ref,
        CHAIRS.source_ref,
    ]
    # The label is not repeated inside the details.
    assert lines[0]["details"].startswith("Item: Tektronix oscilloscope")
    assert (
        "matching_purchases" in ask["system"].split("DATA\n", 1)[0]
    )  # rules explain it
    assert ask["response"].record_counts["matching_purchase_lines"] == 2


def test_sources_list_only_the_purchase_lines_the_answer_cites(ask):
    response = ask["run"]()

    assert [(s.type, s.ref) for s in response.sources] == [
        ("sql_calculation", "Budget figures"),
        ("pr_line", OSCILLOSCOPE.source_ref),
    ]
    assert (
        response.sources[1].detail
        == "Tektronix oscilloscope · Embedded Lab · 2026-05-04"
    )


def test_uncited_hits_and_invented_refs_are_not_sources(ask):
    ask["answer"] = "Nothing matched, though see [PR 1111111111 line 9]."

    response = ask["run"]()

    assert [s.type for s in response.sources] == ["sql_calculation"]


def test_default_window_is_the_current_fiscal_year(ask):
    ask["run"]()

    call = ask["search_calls"][0]
    assert call["limit"] == chatbot_answer_service.MATCHING_PURCHASE_LIMIT
    assert (
        call["start"] is not None
        and call["start"].month == 4
        and call["start"].day == 1
    )
    assert call["end"] is not None and call["end"].month == 3 and call["end"].day == 31


def test_dashboard_window_is_used_for_the_search(ask):
    ask["run"](start_date=date(2026, 7, 1), end_date=date(2026, 9, 28))

    call = ask["search_calls"][0]
    assert (call["start"], call["end"]) == (date(2026, 7, 1), date(2026, 9, 28))


def test_pending_question_searches_pending_lines(ask):
    ask["run"]("Do we have pending calibration purchases?")

    call = ask["search_calls"][0]
    assert call["approved_only"] is False
    assert call["status_prefix"] == "pending"
    block = _facts(ask["system"])["matching_purchases"]
    assert "pending purchase lines" in block["note"]


def test_empty_pending_semantic_match_keeps_recent_purchase_fallback(ask):
    ask["hits"] = []

    ask["run"]("Show me pending purchases awaiting approval")

    facts = _facts(ask["system"])
    assert (
        "does not mean there are no pending lines"
        in facts["matching_purchases"]["note"]
    )
    assert "recent_purchases" in facts


def test_embeddings_off_skips_search_silently(ask, monkeypatch):
    monkeypatch.setattr(embedding_client, "embedding_configured", lambda: False)

    response = ask["run"]()

    assert ask["search_calls"] == []
    assert "matching_purchases" not in _facts(ask["system"])
    assert response.notes == []
    assert response.record_counts["matching_purchase_lines"] == 0


def test_embedding_failure_falls_back_to_figures_with_a_note(ask):
    ask["search_error"] = EmbeddingUnavailableError("provider down")

    response = ask["run"]()

    assert "matching_purchases" not in _facts(ask["system"])
    assert response.answer  # still answered from the fact sheet
    assert any(
        note.startswith("Purchase search is unavailable") for note in response.notes
    )


def test_database_error_rolls_back_and_falls_back(ask):
    ask["search_error"] = ProgrammingError(
        "SELECT", {}, Exception("no knowledge_chunks")
    )
    db = _FakeDb()

    response = ask["run"](db=db)

    assert db.rolled_back is True
    assert any(
        note.startswith("Purchase search is unavailable") for note in response.notes
    )


def test_no_close_hits_tells_the_model_nothing_matched(ask):
    ask["hits"] = []

    response = ask["run"]()

    block = _facts(ask["system"])["matching_purchases"]
    assert block["lines"] == []
    assert block["note"].startswith("No approved purchase lines")
    assert [s.type for s in response.sources] == ["sql_calculation"]


def test_line_1_citation_is_not_found_inside_line_10(ask):
    line_1 = _hit("PR 4500012345 line 1", "Probe kit")
    line_10 = _hit("PR 4500012345 line 10", "Oscilloscope")
    ask["hits"] = [line_1, line_10]
    ask["answer"] = "You bought one [PR 4500012345 line 10]."

    response = ask["run"]()

    assert [s.ref for s in response.sources if s.type == "pr_line"] == [
        line_10.source_ref
    ]


def test_citation_must_be_the_whole_label(ask):
    hit = _hit("PR 45 line 1", "Probe kit")
    ask["hits"] = [hit]

    ask["answer"] = "See [PR 4545 line 1] and XPR 45 line 1."
    assert [s.type for s in ask["run"]().sources] == ["sql_calculation"]

    ask["answer"] = "See [PR 45 line 1]."
    assert [s.ref for s in ask["run"]().sources][1:] == ["PR 45 line 1"]


def test_union_window_covers_every_period():
    fy25 = (date(2025, 4, 1), date(2026, 3, 31))
    fy26 = (date(2026, 4, 1), date(2027, 3, 31))

    assert _union_window([fy25, fy26]) == (date(2025, 4, 1), date(2027, 3, 31))
    assert _union_window([fy25, (None, None)]) == (None, None)
    assert _union_window([]) == (None, None)
