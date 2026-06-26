"""
W9-02 done-gate tests requested by Harry:
duplicate / versioning / history edge cases + audit trail completeness.

Each test runs in a SAVEPOINT (see conftest.db fixture) so writes don't
persist to the budget_system DB.
"""
from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.review import (
    CorrectionRequest,
    commit_batch,
    correct_queue_item,
)
from app.models.staging import (
    AuditLog,
    PRVersion,
    PurchaseRequest,
    PurchaseRequestLine,
    ReviewAction,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
)
from app.models.upload import PRLineItem, UploadMetadata
from app.repositories.persistence_repository import persist_upload_to_db


# ─── Commit: duplicate / versioning / history ────────────────────────────


def test_commit_creates_pr_and_version(db, admin_user, make_staging_batch):
    """First commit of a never-seen source_pr_number → 1 PR + 1 'created' version."""
    batch = make_staging_batch(source_pr_number="PR-W902-CREATE")

    response = commit_batch(batch.batch_id, db=db, current_user=admin_user)

    assert response.success is True
    assert response.prs_created == 1
    assert response.prs_updated == 0

    prs = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == "PR-W902-CREATE")
        .all()
    )
    assert len(prs) == 1

    versions = db.query(PRVersion).filter(PRVersion.pr_id == prs[0].pr_id).all()
    assert len(versions) == 1
    assert versions[0].change_type == "created"
    assert versions[0].old_data is None
    assert versions[0].new_data is not None
    assert versions[0].new_data["source_pr_number"] == "PR-W902-CREATE"


def test_recommit_same_pr_updates_in_place(db, admin_user, make_staging_batch):
    """Re-uploading the same source_pr_number with a different amount must
    UPDATE in place — not create a duplicate purchase_requests row."""
    batch_1 = make_staging_batch(
        source_pr_number="PR-W902-UPDATE",
        grand_total=Decimal("1000.00"),
    )
    commit_batch(batch_1.batch_id, db=db, current_user=admin_user)

    batch_2 = make_staging_batch(
        source_pr_number="PR-W902-UPDATE",
        grand_total=Decimal("2500.00"),
    )
    response = commit_batch(batch_2.batch_id, db=db, current_user=admin_user)

    assert response.prs_created == 0
    assert response.prs_updated == 1

    prs = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == "PR-W902-UPDATE")
        .all()
    )
    assert len(prs) == 1, "Re-upload must NOT create a duplicate PR row."
    assert prs[0].grand_total_sgd == Decimal("2500.00")
    assert prs[0].latest_batch_id == batch_2.batch_id

    versions = (
        db.query(PRVersion)
        .filter(PRVersion.pr_id == prs[0].pr_id)
        .order_by(PRVersion.version_id)
        .all()
    )
    assert len(versions) == 2
    assert versions[0].change_type == "created"
    assert versions[0].old_data is None
    assert versions[1].change_type == "updated"
    assert versions[1].old_data is not None
    assert versions[1].old_data["grand_total_sgd"] == "1000.00"
    assert versions[1].new_data["grand_total_sgd"] == "2500.00"


def test_recommit_replaces_all_lines(db, admin_user, make_staging_batch):
    """A re-uploaded PR with a different set of lines must REPLACE the
    existing lines, not append to them."""
    batch_1 = make_staging_batch(
        source_pr_number="PR-W902-LINES",
        lines=[
            ("old item A", Decimal("50.00")),
            ("old item B", Decimal("50.00")),
        ],
    )
    commit_batch(batch_1.batch_id, db=db, current_user=admin_user)

    batch_2 = make_staging_batch(
        source_pr_number="PR-W902-LINES",
        lines=[("new single item", Decimal("999.00"))],
    )
    commit_batch(batch_2.batch_id, db=db, current_user=admin_user)

    pr = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == "PR-W902-LINES")
        .one()
    )
    final_lines = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.pr_id == pr.pr_id)
        .all()
    )
    assert len(final_lines) == 1, "Old lines must be deleted on re-upload."
    assert final_lines[0].item_description == "new single item"
    assert final_lines[0].amount_gst == Decimal("999.00")


def test_source_staging_line_id_traceability(db, admin_user, make_staging_batch):
    """Every committed purchase_request_lines row must link back to a real
    staging_pr_lines row via source_staging_line_id."""
    batch = make_staging_batch(
        source_pr_number="PR-W902-TRACE",
        lines=[("traceable item", Decimal("123.45"))],
    )
    commit_batch(batch.batch_id, db=db, current_user=admin_user)

    pr = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == "PR-W902-TRACE")
        .one()
    )
    final_line = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.pr_id == pr.pr_id)
        .one()
    )
    assert final_line.source_staging_line_id is not None
    staging_line = (
        db.query(StagingPRLine)
        .filter(StagingPRLine.staging_line_id == final_line.source_staging_line_id)
        .one_or_none()
    )
    assert staging_line is not None, "source_staging_line_id must point to a real staging row."
    assert staging_line.item_details == "traceable item"


# ─── Audit trail ─────────────────────────────────────────────────────────


def test_commit_writes_audit_log(db, admin_user, make_staging_batch):
    """Commit writes one BATCH_COMMITTED audit_logs row with the right counts."""
    batch = make_staging_batch(source_pr_number="PR-W902-AUDIT-COMMIT")
    commit_batch(batch.batch_id, db=db, current_user=admin_user)

    rows = (
        db.query(AuditLog)
        .filter(AuditLog.action_type == "BATCH_COMMITTED")
        .filter(AuditLog.record_id == str(batch.batch_id))
        .all()
    )
    assert len(rows) == 1
    audit = rows[0]
    assert audit.user_id == admin_user.user_id
    assert audit.new_value["prs_created"] == 1
    assert audit.new_value["prs_updated"] == 0
    assert audit.new_value["lines_created"] == 1
    assert audit.new_value["upload_status"] == "committed"


def test_correction_writes_review_action_and_audit_log(
    db, admin_user, make_staging_batch, seed_refs
):
    """A correction writes exactly one review_actions row + one
    REVIEW_RESOLVED audit_logs row, capturing reviewer + old/new state."""
    batch = make_staging_batch(
        source_pr_number="PR-W902-AUDIT-CORRECT",
        needs_review=True,
    )
    queue_item = (
        db.query(ReviewQueueItem)
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .one()
    )

    correct_queue_item(
        queue_item.review_queue_id,
        CorrectionRequest(
            lab_group_id=seed_refs["lab_group_id"],
            lab_id=seed_refs["lab_id"],
            category_id=seed_refs["category_id"],
            comment="test correction",
        ),
        db=db,
        current_user=admin_user,
    )

    actions = (
        db.query(ReviewAction)
        .filter(ReviewAction.review_queue_id == queue_item.review_queue_id)
        .all()
    )
    assert len(actions) == 1
    assert actions[0].reviewed_by == admin_user.user_id
    assert actions[0].action_type == "corrected"
    assert actions[0].review_comment == "test correction"

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.action_type == "REVIEW_RESOLVED")
        .filter(AuditLog.record_id == str(queue_item.review_queue_id))
        .all()
    )
    assert len(audits) == 1
    assert audits[0].user_id == admin_user.user_id
    assert audits[0].old_value is not None
    assert audits[0].new_value["review_status"] == "resolved"


def test_upload_writes_audit_log(db, admin_user, seed_refs):
    """persist_upload_to_db writes one UPLOAD_RECEIVED audit_logs row."""
    metadata = UploadMetadata.create(
        batch_id="UP-TEST",
        filename="test_upload.xlsx",
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
    )
    classified_items = [
        {
            "item": PRLineItem(
                row_number=1,
                pr_number="PR-W902-UPLOAD-AUDIT",
                pr_sub_date="2026-06-01",
                requestor="Tester",
                purpose="Upload audit test",
                grand_total_sgd=Decimal("10.00"),
                item_details="one item",
                quantity=Decimal("1"),
                unit_rate=Decimal("10.00"),
                wbs="WBS-TEST",
                instruction_to_vendor="",
                pr_category="General",
                amount_gst=Decimal("10.00"),
                line_identity_key="key1",
                content_hash="hash1",
            ),
            "classification": {
                "lab_id": seed_refs["lab_id"],
                "lab_group_id": seed_refs["lab_group_id"],
                "reason": "test classification",
            },
        }
    ]

    counts = persist_upload_to_db(
        db=db,
        metadata=metadata,
        classified_items=classified_items,
        current_user=admin_user,
    )
    batch_id = counts["db_batch_id"]

    audits = (
        db.query(AuditLog)
        .filter(AuditLog.action_type == "UPLOAD_RECEIVED")
        .filter(AuditLog.record_id == str(batch_id))
        .all()
    )
    assert len(audits) == 1
    assert audits[0].user_id == admin_user.user_id
    assert audits[0].new_value["filename"] == "test_upload.xlsx"
    assert audits[0].new_value["file_type"] == "xlsx"
    assert audits[0].new_value["lines_inserted"] == 1
    assert audits[0].new_value["headers_inserted"] == 1


# ─── Lifecycle guards ────────────────────────────────────────────────────


def test_commit_blocked_when_already_committed(db, admin_user, make_staging_batch):
    """A second commit on the same batch must 409, not duplicate rows."""
    batch = make_staging_batch(source_pr_number="PR-W902-LOCK-COMMIT")
    commit_batch(batch.batch_id, db=db, current_user=admin_user)

    with pytest.raises(HTTPException) as exc_info:
        commit_batch(batch.batch_id, db=db, current_user=admin_user)
    assert exc_info.value.status_code == 409


def test_correction_blocked_after_commit(
    db, admin_user, make_staging_batch, seed_refs
):
    """Correcting a queue item on a batch that is already committed must 409."""
    batch = make_staging_batch(
        source_pr_number="PR-W902-LOCK-CORRECT",
        needs_review=True,
    )
    queue_item = (
        db.query(ReviewQueueItem)
        .join(StagingPRLine, StagingPRLine.staging_line_id == ReviewQueueItem.staging_line_id)
        .join(StagingPRHeader, StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id)
        .filter(StagingPRHeader.batch_id == batch.batch_id)
        .one()
    )
    # Resolve the open item so commit can proceed.
    correct_queue_item(
        queue_item.review_queue_id,
        CorrectionRequest(
            lab_group_id=seed_refs["lab_group_id"],
            lab_id=seed_refs["lab_id"],
            category_id=seed_refs["category_id"],
        ),
        db=db,
        current_user=admin_user,
    )
    commit_batch(batch.batch_id, db=db, current_user=admin_user)

    # Now attempt another correction on the same item — should be blocked.
    with pytest.raises(HTTPException) as exc_info:
        correct_queue_item(
            queue_item.review_queue_id,
            CorrectionRequest(
                lab_group_id=seed_refs["lab_group_id"],
                lab_id=seed_refs["lab_id"],
                category_id=seed_refs["category_id"],
            ),
            db=db,
            current_user=admin_user,
        )
    assert exc_info.value.status_code == 409
