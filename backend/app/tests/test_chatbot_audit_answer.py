"""Admin-only audit evidence supplied to Ask AI."""

import pytest

from app.models.auth import User
from app.models.staging import AuditLog
from app.services.chatbot_answer_service import (
    _answer_sources,
    _audit_events,
    _audit_fallback_answer,
)


def test_admin_can_retrieve_recent_audit_events(db, admin_user):
    log = AuditLog(
        user_id=admin_user.user_id,
        action_type="UPDATE",
        entity_name="Budget",
        record_id="test-budget-17",
        old_value={"budget_amount": "1000"},
        new_value={"budget_amount": "1200"},
    )
    db.add(log)
    db.flush()

    result = _audit_events(
        db,
        admin_user,
        "What changed in the audit log?",
        [(None, None)],
    )

    assert result is not None
    event = next(
        item for item in result["events"] if item["source"] == f"Audit #{log.audit_id}"
    )
    assert event["actor"] == admin_user.full_name
    assert event["action"] == "UPDATE"
    assert event["target_record"] == "test-budget-17"
    assert event["old_value"] == {"budget_amount": "1000"}
    assert event["new_value"] == {"budget_amount": "1200"}


def test_non_admin_is_not_given_audit_records(db):
    user = db.query(User).filter(User.email == "teamlead.fcb@test.com").first()
    if user is None:
        pytest.skip("Seed Team Lead is missing.")

    result = _audit_events(db, user, "Show the audit log", [(None, None)])

    assert result == {
        "note": "System audit history is restricted to Administrators.",
        "events": [],
    }


def test_cited_audit_event_is_returned_as_a_source():
    event = {
        "source": "Audit #42",
        "action": "UPDATE",
        "module": "Budget",
        "target_record": "17",
        "actor": "Test Admin",
    }

    sources = _answer_sources(
        "Test Admin changed the budget [Audit #42].",
        "FY2026",
        [],
        [event],
    )

    assert [(source.type, source.ref) for source in sources] == [
        ("sql_calculation", "Budget figures"),
        ("audit_event", "Audit #42"),
    ]


def test_audit_fallback_answer_is_cited_and_names_actor():
    answer = _audit_fallback_answer(
        {
            "events": [
                {
                    "source": "Audit #42",
                    "timestamp": "2026-10-20T10:30:00",
                    "actor": "Test Admin",
                    "action": "UPDATE",
                    "module": "Budget",
                    "target_record": "17",
                }
            ]
        }
    )

    assert "Test Admin performed UPDATE on Budget (17)" in answer
    assert "[Audit #42]" in answer
