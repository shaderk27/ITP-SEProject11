"""
W17 Approved status protection: once a committed PR line is Approved (any
"Approved..." variant), a later upload cannot change it to Pending, Rejected,
Cancelled, blank or any other non-Approved status. Only that line is skipped;
the rest of the batch commits normally.

Runs the real path: UploadService -> persist_upload_to_db -> commit_batch on
PostgreSQL, inside the conftest.db savepoint so nothing persists. Each upload
gets a fresh (missing) JSON store unless a test passes one in, so the guard is
proven not to depend on backend/.data/upload_store.json.
"""

from __future__ import annotations

from io import BytesIO
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import BackgroundTasks

from app.api.review import commit_batch
from app.models.staging import (
    AuditLog,
    PRVersion,
    PurchaseRequest,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
)
from app.repositories.upload_repository import UploadRepository
from app.services.duplicate_service import is_status_regression
from app.services.upload_service import UploadService

PR_A = "PR-W17-GUARD-A"
PR_B = "PR-W17-GUARD-B"
PR_C = "PR-W17-GUARD-C"


def _row(pr: str, status: str, item: str = "Widget A") -> dict:
    return {
        "PR": pr,
        "PR Status": status,
        "PR Sub Date": "01/06/2026",
        "Requestor": "W17 Tester",
        "Purpose": "Status guard",
        "Grand Total in SGD": 100,
        "Item Details": item,
        "Qty": 1,
        "Unit Rate": 100,
        "WBS": "WBS-W17-1",
    }


def _xlsx(rows: list[dict]) -> bytes:
    buf = BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _upload(db, user, tmp_path, rows, store=None) -> dict:
    store = store or tmp_path / f"missing-{uuid4().hex}.json"
    service = UploadService(UploadRepository(store), db=db)
    return service.process_upload(
        filename="w17.xlsx",
        content=_xlsx(rows),
        uploader_email=user.email,
        uploader_name=user.full_name,
        uploader_role="admin",
        current_user=user,
    )


def _commit(db, user, upload_result):
    batch_id = upload_result["persistence"]["db_batch_id"]
    # Close classifier review items so the commit isn't blocked.
    for item in (
        db.query(ReviewQueueItem)
        .join(StagingPRLine)
        .join(StagingPRHeader)
        .filter(StagingPRHeader.batch_id == batch_id)
        .all()
    ):
        item.queue_status = "resolved"
    db.flush()
    tasks = BackgroundTasks()
    response = commit_batch(batch_id, tasks, db=db, current_user=user)
    return response, tasks


def _upload_commit(db, user, tmp_path, rows, store=None):
    return _commit(db, user, _upload(db, user, tmp_path, rows, store))


def _pr(db, pr_number: str) -> PurchaseRequest:
    pr = db.query(PurchaseRequest).filter_by(source_pr_number=pr_number).one()
    db.refresh(pr)
    return pr


def _pending_then_approved(db, user, tmp_path, store=None):
    _upload_commit(db, user, tmp_path, [_row(PR_A, "Pending")], store)
    _upload_commit(db, user, tmp_path, [_row(PR_A, "Approved")], store)


# ─── Helper ──────────────────────────────────────────────────────────────


def test_is_status_regression_variants():
    # Approved -> anything non-Approved is blocked.
    assert is_status_regression("Approved", "Pending")
    assert is_status_regression("Approved (SVP)", "Pending Procurement Review")
    assert is_status_regression(" approved (finance) ", "PENDING")
    assert is_status_regression("Approved", "Rejected")
    assert is_status_regression("Approved (Procurement)", " cancelled ")
    assert is_status_regression("Approved", "On Hold")
    assert is_status_regression("Approved", "")
    assert is_status_regression("Approved", "   ")
    assert is_status_regression("Approved", None)
    # Approved -> another Approved variant, and anything -> Approved, may proceed.
    assert not is_status_regression("Approved", "Approved (SVP)")
    assert not is_status_regression("APPROVED (SVP)", " approved ")
    assert not is_status_regression("Pending", "Approved")
    assert not is_status_regression("Rejected", "Approved (Finance)")
    # Nothing is protected until a line is Approved.
    assert not is_status_regression("Rejected", "Pending")
    assert not is_status_regression("Pending", "Rejected")
    assert not is_status_regression(None, "Pending")
    assert not is_status_regression("", "Cancelled")


# ─── Core scenario ───────────────────────────────────────────────────────


def test_pending_commits_then_approved_updates_in_place(db, admin_user, tmp_path):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Pending")])
    pr = _pr(db, PR_A)
    assert pr.pr_status == "Pending"
    assert [line.pr_status for line in pr.lines] == ["Pending"]

    response, _ = _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    pr = _pr(db, PR_A)
    assert response.prs_updated == 1
    assert response.status_regressions_skipped == 0
    assert pr.pr_status == "Approved"
    assert [line.pr_status for line in pr.lines] == ["Approved"]


def test_later_pending_is_skipped_and_approved_kept(db, admin_user, tmp_path):
    _pending_then_approved(db, admin_user, tmp_path)
    before = _pr(db, PR_A)
    accepted_staging_id = before.lines[0].source_staging_line_id

    upload = _upload(db, admin_user, tmp_path, [_row(PR_A, "Pending")])
    assert upload["counts"]["status_regressions_skipped"] == 1
    # No review queue item for the skipped line.
    batch_id = upload["persistence"]["db_batch_id"]
    assert upload["persistence"]["queue_items_inserted"] == 0

    response, tasks = _commit(db, admin_user, upload)
    pr = _pr(db, PR_A)

    assert response.success
    assert response.new_upload_status == "committed"
    assert response.status_regressions_skipped == 1
    assert pr.pr_status == "Approved"
    assert len(pr.lines) == 1
    assert pr.lines[0].pr_status == "Approved"
    assert pr.lines[0].source_staging_line_id == accepted_staging_id

    staging = (
        db.query(StagingPRLine)
        .join(StagingPRHeader)
        .filter(StagingPRHeader.batch_id == batch_id)
        .one()
    )
    assert staging.duplicate_status == "status_regression"

    # Skipped-only batch queues no threshold or vector work.
    assert response.pr_ids == []
    assert tasks.tasks == []


def test_skipped_attempt_recorded_in_history_and_audit(db, admin_user, tmp_path):
    _pending_then_approved(db, admin_user, tmp_path)
    response, _ = _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Pending")])
    pr = _pr(db, PR_A)

    version = (
        db.query(PRVersion).filter_by(pr_id=pr.pr_id, batch_id=response.batch_id).one()
    )
    assert version.new_data["pr_status"] == "Approved"
    skipped = version.new_data["status_regressions_skipped"]
    assert len(skipped) == 1
    assert skipped[0]["accepted_status"] == "Approved"
    assert skipped[0]["attempted_status"] == "Pending"
    assert version.changed_by == admin_user.user_id

    audit = (
        db.query(AuditLog)
        .filter_by(action_type="BATCH_COMMITTED", record_id=str(response.batch_id))
        .one()
    )
    assert audit.new_value["status_regressions_skipped"] == 1
    assert audit.user_id == admin_user.user_id


def test_approved_variant_protected_from_pending_variant(db, admin_user, tmp_path):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved (SVP)")])
    response, _ = _upload_commit(
        db, admin_user, tmp_path, [_row(PR_A, "Pending Procurement Review")]
    )
    pr = _pr(db, PR_A)
    assert response.status_regressions_skipped == 1
    assert pr.pr_status == "Approved (SVP)"
    assert pr.lines[0].pr_status == "Approved (SVP)"


@pytest.mark.parametrize(
    "incoming", ["Pending", "Rejected", "Cancelled", "On Hold", "rejected (finance)"]
)
def test_approved_is_final_against_any_other_status(db, admin_user, tmp_path, incoming):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    upload = _upload(db, admin_user, tmp_path, [_row(PR_A, incoming)])
    assert upload["counts"]["status_regressions_skipped"] == 1
    assert upload["counts"]["accepted"] == 0
    assert incoming in upload["records"]["status_regression"][0]["reason"]

    response, tasks = _commit(db, admin_user, upload)
    pr = _pr(db, PR_A)

    assert response.status_regressions_skipped == 1
    assert pr.pr_status == "Approved"
    assert [line.pr_status for line in pr.lines] == ["Approved"]
    assert tasks.tasks == []

    version = (
        db.query(PRVersion).filter_by(pr_id=pr.pr_id, batch_id=response.batch_id).one()
    )
    skipped = version.new_data["status_regressions_skipped"]
    assert [(s["accepted_status"], s["attempted_status"]) for s in skipped] == [
        ("Approved", incoming)
    ]
    audit = (
        db.query(AuditLog)
        .filter_by(action_type="BATCH_COMMITTED", record_id=str(response.batch_id))
        .one()
    )
    assert audit.new_value["status_regressions_skipped"] == 1


def test_approved_to_another_approved_variant_proceeds(db, admin_user, tmp_path):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    response, _ = _upload_commit(
        db, admin_user, tmp_path, [_row(PR_A, "Approved (Finance)")]
    )
    pr = _pr(db, PR_A)
    assert response.status_regressions_skipped == 0
    assert pr.pr_status == "Approved (Finance)"
    assert [line.pr_status for line in pr.lines] == ["Approved (Finance)"]


def test_rejected_to_approved_proceeds(db, admin_user, tmp_path):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Rejected")])
    response, _ = _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    pr = _pr(db, PR_A)
    assert response.status_regressions_skipped == 0
    assert pr.pr_status == "Approved"
    assert [line.pr_status for line in pr.lines] == ["Approved"]


def test_blank_status_upload_is_rejected_by_validation(db, admin_user, tmp_path):
    """A blank PR Status never reaches commit through the upload page."""
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    upload = _upload(db, admin_user, tmp_path, [_row(PR_A, "")])
    assert upload["success"] is False
    assert any("PR Status" in e["field"] for e in upload["validation_errors"])
    assert _pr(db, PR_A).pr_status == "Approved"


def _set_status(batch, db, status: str) -> None:
    for header in db.query(StagingPRHeader).filter_by(batch_id=batch.batch_id):
        for line in db.query(StagingPRLine).filter_by(
            staging_header_id=header.staging_header_id
        ):
            line.raw_line_json = {**line.raw_line_json, "pr_status": status}
    db.flush()


@pytest.mark.parametrize("incoming", ["", "   "])
def test_blank_status_blocked_at_commit(db, admin_user, make_staging_batch, incoming):
    """Commit is the authoritative check, even for a blank incoming status."""
    approved = make_staging_batch(source_pr_number=PR_A)
    _set_status(approved, db, "Approved (SVP)")
    commit_batch(approved.batch_id, BackgroundTasks(), db=db, current_user=admin_user)

    blank = make_staging_batch(source_pr_number=PR_A)
    _set_status(blank, db, incoming)
    response = commit_batch(
        blank.batch_id, BackgroundTasks(), db=db, current_user=admin_user
    )
    pr = _pr(db, PR_A)

    assert response.status_regressions_skipped == 1
    assert pr.pr_status == "Approved (SVP)"
    assert [line.pr_status for line in pr.lines] == ["Approved (SVP)"]


# ─── Mixed batches ───────────────────────────────────────────────────────


def test_mixed_batch_only_regressing_line_skipped(db, admin_user, tmp_path):
    _pending_then_approved(db, admin_user, tmp_path)  # PR_A is Approved
    _upload_commit(db, admin_user, tmp_path, [_row(PR_C, "Pending")])

    upload = _upload(
        db,
        admin_user,
        tmp_path,
        [
            _row(PR_A, "Pending"),  # regression -> skipped
            _row(PR_B, "Pending"),  # new PR -> inserted
            _row(PR_C, "Approved"),  # valid update
        ],
    )
    assert upload["counts"]["status_regressions_skipped"] == 1
    # Fresh JSON store: all three look new, but the skipped one is listed
    # in its own bucket, not under accepted.
    assert upload["counts"]["accepted"] == 2
    assert [r["line"]["pr_number"] for r in upload["records"]["inserted"]] == [
        PR_B,
        PR_C,
    ]
    regressions = upload["records"]["status_regression"]
    assert [r["line"]["pr_number"] for r in regressions] == [PR_A]
    assert regressions[0]["status"] == "status_regression"
    assert "Already Approved" in regressions[0]["reason"]
    assert "status_regression_rows" not in upload["persistence"]

    response, _ = _commit(db, admin_user, upload)

    assert response.status_regressions_skipped == 1
    assert response.prs_created == 1
    assert response.prs_updated == 2
    assert response.lines_created == 1
    assert _pr(db, PR_A).pr_status == "Approved"
    assert _pr(db, PR_B).pr_status == "Pending"
    assert _pr(db, PR_C).pr_status == "Approved"

    # Only PRs with applied lines are reindexed.
    assert _pr(db, PR_A).pr_id not in response.pr_ids
    assert _pr(db, PR_B).pr_id in response.pr_ids
    assert _pr(db, PR_C).pr_id in response.pr_ids


def test_new_line_under_same_pr_still_inserts(db, admin_user, tmp_path):
    _pending_then_approved(db, admin_user, tmp_path)
    response, _ = _upload_commit(
        db,
        admin_user,
        tmp_path,
        [_row(PR_A, "Pending"), _row(PR_A, "Pending", item="Widget B")],
    )
    pr = _pr(db, PR_A)
    statuses = {line.item_description: line.pr_status for line in pr.lines}

    assert response.status_regressions_skipped == 1
    assert response.lines_created == 1
    assert statuses == {"Widget A": "Approved", "Widget B": "Pending"}
    # Header follows the first line's accepted state.
    assert pr.pr_status == "Approved"
    assert pr.pr_id in response.pr_ids


# ─── Existing behaviour kept ─────────────────────────────────────────────


def test_exact_duplicate_keeps_duplicate_behaviour(db, admin_user, tmp_path):
    store = tmp_path / "shared.json"
    _pending_then_approved(db, admin_user, tmp_path, store)

    upload = _upload(db, admin_user, tmp_path, [_row(PR_A, "Approved")], store)
    assert upload["counts"]["duplicate_skipped"] == 1
    assert upload["counts"]["status_regressions_skipped"] == 0
    assert upload["records"]["status_regression"] == []
    assert upload["persistence"] == {}


def test_guard_works_with_populated_json_store(db, admin_user, tmp_path):
    store = tmp_path / "shared.json"
    _pending_then_approved(db, admin_user, tmp_path, store)
    upload = _upload(db, admin_user, tmp_path, [_row(PR_A, "Pending")], store)
    # The JSON store calls it a reupload update; it is moved out of that list.
    assert upload["counts"]["reupload_updated"] == 0
    assert upload["records"]["updated"] == []
    assert len(upload["records"]["status_regression"]) == 1
    assert upload["counts"]["status_regressions_skipped"] == 1

    response, _ = _commit(db, admin_user, upload)
    assert response.status_regressions_skipped == 1
    assert _pr(db, PR_A).pr_status == "Approved"


def test_reviewed_classification_unchanged(db, admin_user, tmp_path, seed_refs):
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Pending")])
    line = _pr(db, PR_A).lines[0]
    line.lab_id = seed_refs["lab_id"]
    line.category_id = seed_refs["category_id"]
    db.flush()

    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Approved")])
    _upload_commit(db, admin_user, tmp_path, [_row(PR_A, "Pending")])

    line = _pr(db, PR_A).lines[0]
    assert line.pr_status == "Approved"
    assert line.lab_id == seed_refs["lab_id"]
    assert line.category_id == seed_refs["category_id"]


def test_multi_file_upload_combines_regressions(db, admin_user, tmp_path):
    from app.api.upload import _combine_batch_results

    _pending_then_approved(db, admin_user, tmp_path)
    first = _upload(db, admin_user, tmp_path, [_row(PR_A, "Pending")])
    second = _upload(db, admin_user, tmp_path, [_row(PR_B, "Pending")])

    combined = _combine_batch_results(
        [first, second], admin_user.email, admin_user.full_name, "admin"
    )
    assert combined["counts"]["status_regressions_skipped"] == 1
    assert combined["counts"]["accepted"] == 1
    assert [
        r["line"]["pr_number"] for r in combined["records"]["status_regression"]
    ] == [PR_A]
    assert [r["line"]["pr_number"] for r in combined["records"]["inserted"]] == [PR_B]


def test_move_status_regressions_rebuckets_and_sorts():
    def rec(row, status="Pending"):
        return {
            "status": "x",
            "reason": "",
            "line": {"row_number": row, "pr_status": status},
        }

    records = {
        "inserted": [rec(2), rec(7)],
        "updated": [rec(3, "Pending Procurement Review"), rec(5)],
        "duplicate": [],
        "status_regression": [],
    }
    UploadService._move_status_regressions(
        records, {7: "Approved", 3: "Approved (SVP)"}
    )

    assert [r["line"]["row_number"] for r in records["inserted"]] == [2]
    assert [r["line"]["row_number"] for r in records["updated"]] == [5]
    moved = records["status_regression"]
    assert [r["line"]["row_number"] for r in moved] == [3, 7]
    assert moved[0]["reason"] == (
        "Already Approved (SVP) in final records; this file says "
        "Pending Procurement Review. Approved status is final, so this line "
        "is skipped at commit."
    )
    assert all(r["status"] == "status_regression" for r in moved)
