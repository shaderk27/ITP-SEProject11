"""
A re-upload with a changed amount updates the saved line, so the dashboard and
the PR total agree. Reviewed lab and category stay, and Approved stays final.

Runs the real path: UploadService -> persist_upload_to_db -> commit_batch on
PostgreSQL, inside the conftest.db savepoint so nothing persists.
"""

from __future__ import annotations

from decimal import Decimal
from io import BytesIO

import pandas as pd
import pytest
from fastapi import BackgroundTasks

from app.api.review import commit_batch
from app.models.config import Lab, LabGroup
from app.models.staging import (
    PRVersion,
    PurchaseRequest,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
)
from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService

PR = "PR-AMOUNT-1"


def _row(status="Pending Support", amount=100, item="Widget A", **overrides) -> dict:
    return {
        "PR": PR,
        "PR Status": status,
        "PR Sub Date": "01/06/2026",
        "Requestor": "Amount Tester",
        "Purpose": "Amount test",
        "Grand Total in SGD": amount,
        "Item Details": item,
        "Qty": 1,
        "Unit Rate": amount,
        "WBS": "WBS-AMOUNT-1",
        **overrides,
    }


@pytest.fixture
def save(db, admin_user, tmp_path):
    store = tmp_path / "store.json"

    def _save(rows: list[dict]) -> dict:
        buffer = BytesIO()
        pd.DataFrame(rows).to_excel(buffer, index=False, engine="openpyxl")
        result = UploadService(UploadRepository(store), db=db).process_upload(
            filename="amount.xlsx",
            content=buffer.getvalue(),
            uploader_email=admin_user.email,
            uploader_name=admin_user.full_name,
            uploader_role="admin",
            current_user=admin_user,
        )
        batch_id = result["persistence"]["db_batch_id"]
        for item in (
            db.query(ReviewQueueItem)
            .join(StagingPRLine)
            .join(StagingPRHeader)
            .filter(StagingPRHeader.batch_id == batch_id)
            .all()
        ):
            item.queue_status = "resolved"
        db.flush()
        commit_batch(batch_id, BackgroundTasks(), db=db, current_user=admin_user)
        return result

    return _save


def _pr(db) -> PurchaseRequest:
    db.expire_all()
    return db.query(PurchaseRequest).filter_by(source_pr_number=PR).one()


def _latest_version(db, pr: PurchaseRequest) -> PRVersion:
    return (
        db.query(PRVersion)
        .filter_by(pr_id=pr.pr_id)
        .order_by(PRVersion.version_id.desc())
        .first()
    )


def test_changed_amount_updates_the_saved_line(db, save) -> None:
    save([_row()])

    result = save([_row(amount=150)])

    pr = _pr(db)
    assert result["counts"]["reupload_updated"] == 1
    assert len(pr.lines) == 1
    assert pr.lines[0].amount_gst == Decimal("150.00")
    assert pr.lines[0].unit_rate == Decimal("150.00")
    assert pr.grand_total_sgd == Decimal("150.00")


def test_amount_and_pending_status_change_together(db, save) -> None:
    save([_row()])

    save([_row("Pending Verification", amount=150)])

    line = _pr(db).lines[0]
    assert line.pr_status == "Pending Verification"
    assert line.amount_gst == Decimal("150.00")


def test_amount_change_is_recorded_in_pr_history(db, save) -> None:
    save([_row()])

    save([_row(amount=150)])

    pr = _pr(db)
    updates = _latest_version(db, pr).new_data["amount_updates"]
    assert len(updates) == 1
    assert Decimal(updates[0]["old_amount"]) == Decimal("100")
    assert Decimal(updates[0]["new_amount"]) == Decimal("150")


def test_status_only_change_records_no_amount_update(db, save) -> None:
    save([_row()])

    save([_row("Pending Verification")])

    pr = _pr(db)
    assert pr.lines[0].amount_gst == Decimal("100.00")
    assert "amount_updates" not in _latest_version(db, pr).new_data


def test_approved_line_amount_can_still_change(db, save) -> None:
    save([_row("Approved (SVP)")])

    save([_row("Approved (SVP)", amount=150)])

    line = _pr(db).lines[0]
    assert line.pr_status == "Approved (SVP)"
    assert line.amount_gst == Decimal("150.00")


def test_blocked_approved_to_pending_line_keeps_its_amount(db, save) -> None:
    save([_row("Approved (SVP)")])

    save([_row("Pending Support", amount=150)])

    line = _pr(db).lines[0]
    assert line.pr_status == "Approved (SVP)"
    assert line.amount_gst == Decimal("100.00")


def test_reviewed_lab_and_category_stay_when_amount_changes(
    db, save, seed_refs
) -> None:
    save([_row()])
    line = _pr(db).lines[0]
    line.lab_id = seed_refs["lab_id"]
    line.category_id = seed_refs["category_id"]
    db.flush()

    save([_row(amount=150)])

    line = _pr(db).lines[0]
    assert line.amount_gst == Decimal("150.00")
    assert line.lab_id == seed_refs["lab_id"]
    assert line.category_id == seed_refs["category_id"]


def test_only_the_changed_line_of_a_pr_updates(db, save) -> None:
    def rows(second_amount):
        total = 100 + second_amount
        return [
            _row(item="Line A", **{"Grand Total in SGD": total, "Unit Rate": 100}),
            _row(
                item="Line B",
                **{"Grand Total in SGD": total, "Unit Rate": second_amount},
            ),
        ]

    save(rows(200))

    save(rows(250))

    amounts = {line.item_description: line.amount_gst for line in _pr(db).lines}
    assert amounts == {"Line A": Decimal("100.00"), "Line B": Decimal("250.00")}


def test_split_line_shares_follow_the_new_amount(db, save) -> None:
    group = LabGroup(lab_group_name="Amount Group", wbs_code="WBS-AMTSPLIT")
    db.add(group)
    db.flush()
    db.add_all(
        [
            Lab(
                lab_group_id=group.lab_group_id,
                lab_code="AMT-ONE",
                lab_name="Amount Lab One",
                is_general=False,
            ),
            Lab(
                lab_group_id=group.lab_group_id,
                lab_code="AMT-TWO",
                lab_name="Amount Lab Two",
                is_general=False,
            ),
        ]
    )
    db.flush()
    split = {"Purpose": "For Amount Lab One and Amount Lab Two", "WBS": "WBS-AMTSPLIT"}

    save([_row(amount=100, **split)])
    assert [line.amount_gst for line in _pr(db).lines] == [
        Decimal("50.00"),
        Decimal("50.00"),
    ]

    save([_row(amount=150, **split)])

    pr = _pr(db)
    assert len(pr.lines) == 2
    assert [line.amount_gst for line in pr.lines] == [
        Decimal("75.00"),
        Decimal("75.00"),
    ]
