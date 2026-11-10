"""
UAT2 feedback: a General lab, a General lab group or a clash between categories
goes to review, category General passes, and reviewers get one plain message
saying what to fix.

Runs the real path: UploadService -> persist_upload_to_db on PostgreSQL, inside
the conftest.db savepoint so nothing persists.
"""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pandas as pd
import pytest

from app.models.auth import Role, User
from app.models.config import Lab, LabGroup, SpendingCategory
from app.models.staging import ReviewQueueItem, StagingPRHeader, StagingPRLine
from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService

WBS = "WBS-REVIEWTEST-1"
NAMED_LAB = "Review Test Named Lab"


@pytest.fixture
def setup(db):
    group = LabGroup(lab_group_name="Review Group", wbs_code=WBS)
    db.add(group)
    db.flush()
    db.add_all(
        [
            Lab(
                lab_group_id=group.lab_group_id,
                lab_code="GEN-RVT",
                lab_name="General",
                is_general=True,
            ),
            Lab(
                lab_group_id=group.lab_group_id,
                lab_code="RVT-NAMED",
                lab_name=NAMED_LAB,
                is_general=False,
            ),
            SpendingCategory(category_name="Reviewtest Supplies"),
            SpendingCategory(category_name="Reviewtest Repairs"),
        ]
    )
    role = db.query(Role).filter(Role.role_name == "admin").first()
    user = User(
        role_id=role.role_id,
        full_name="Review Test Admin",
        email=f"review-{uuid4().hex}@test.com",
        password_hash="x",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _upload(db, user, tmp_path, **overrides) -> tuple[dict, ReviewQueueItem | None]:
    pr_number = f"PR-REVIEW-{uuid4().hex[:8]}"
    row = {
        "PR": pr_number,
        "PR Status": "Pending",
        "PR Sub Date": "01/06/2026",
        "Requestor": "Nobody Known",
        "Purpose": "Monthly order",
        "Req Type": "Reviewtest Supplies",
        "Grand Total in SGD": 100,
        "Item Details": "Widget",
        "Qty": 1,
        "Unit Rate": 100,
        "WBS": WBS,
        **overrides,
    }
    buffer = BytesIO()
    pd.DataFrame([row]).to_excel(buffer, index=False, engine="openpyxl")
    service = UploadService(
        UploadRepository(tmp_path / f"missing-{uuid4().hex}.json"), db=db
    )
    result = service.process_upload(
        filename="review.xlsx",
        content=buffer.getvalue(),
        uploader_email=user.email,
        uploader_name=user.full_name,
        uploader_role="admin",
        current_user=user,
    )
    queue_item = (
        db.query(ReviewQueueItem)
        .join(StagingPRLine)
        .join(StagingPRHeader)
        .filter(StagingPRHeader.source_pr_number == pr_number)
        .first()
    )
    return result, queue_item


def _summary_issue(result: dict) -> str | None:
    return result["records"]["inserted"][0]["line"].get("review_issue")


def test_category_general_with_a_named_lab_passes(db, setup, tmp_path) -> None:
    result, queue_item = _upload(
        db, setup, tmp_path, Purpose=f"For {NAMED_LAB}", **{"Req Type": ""}
    )

    assert queue_item is None
    assert result["counts"]["needs_review"] == 0
    assert _summary_issue(result) is None


def test_general_lab_asks_for_a_lab_in_the_group(db, setup, tmp_path) -> None:
    result, queue_item = _upload(db, setup, tmp_path)

    expected = (
        "Choose a lab. The file doesn't say which Review Group lab this line is for."
    )
    assert queue_item.review_reason == expected
    assert _summary_issue(result) == expected
    assert result["counts"]["needs_review"] == 1


def test_unknown_wbs_asks_for_group_and_lab(db, setup, tmp_path) -> None:
    result, queue_item = _upload(db, setup, tmp_path, WBS="WBS-NOPE-9")

    expected = (
        'Choose a lab group and lab. The WBS code "WBS-NOPE-9" '
        "doesn't match any lab group."
    )
    assert queue_item.review_reason == expected
    assert _summary_issue(result) == expected


def test_named_lab_under_general_lab_group_is_flagged(db, setup, tmp_path) -> None:
    general_group = (
        db.query(LabGroup).filter(LabGroup.lab_group_name == "General").first()
    )
    db.add(
        Lab(
            lab_group_id=general_group.lab_group_id,
            lab_code="RVT-GROUPLAB",
            lab_name="Review Test Group Lab",
            is_general=False,
        )
    )
    db.flush()

    result, queue_item = _upload(
        db, setup, tmp_path, WBS="", Purpose="For Review Test Group Lab"
    )

    expected = "Choose a lab group and lab. This line has no WBS."
    assert queue_item.review_reason == expected
    assert _summary_issue(result) == expected


def test_two_categories_ask_to_choose_one(db, setup, tmp_path) -> None:
    result, queue_item = _upload(
        db,
        setup,
        tmp_path,
        Purpose=f"For {NAMED_LAB}",
        **{"Req Type": "Reviewtest Supplies, Reviewtest Repairs"},
    )

    expected = (
        "Choose one category. The file lists more than one: "
        "Reviewtest Repairs, Reviewtest Supplies."
    )
    assert queue_item.review_reason == expected
    assert _summary_issue(result) == expected


def test_general_lab_and_two_categories_show_both(db, setup, tmp_path) -> None:
    _, queue_item = _upload(
        db,
        setup,
        tmp_path,
        **{"Req Type": "Reviewtest Supplies, Reviewtest Repairs"},
    )

    assert queue_item.review_reason.startswith("Choose a lab.")
    assert "Choose one category." in queue_item.review_reason


def test_review_message_never_mentions_category_general(db, setup, tmp_path) -> None:
    _, queue_item = _upload(db, setup, tmp_path, **{"Req Type": ""})

    assert queue_item.review_reason == (
        "Choose a lab. The file doesn't say which Review Group lab this line is for."
    )
