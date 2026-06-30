"""
Persistence layer for upload pipeline.

Takes the output of Harry's parser + classifier and writes it to:
  - upload_batches        (1 row per upload)
  - staging_pr_headers    (1 row per unique PR number in the file)
  - staging_pr_lines      (1 row per parsed line, with classifier guesses)
  - review_queue_items    (1 row per line that needs human review)
  - audit_logs            (1 row per upload, action_type='UPLOAD_RECEIVED')

Everything happens in a single transaction. If any insert fails,
SQLAlchemy rolls back the whole batch (via the session lifecycle in get_db).
"""

from datetime import datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.config import Lab, LabGroup, SpendingCategory
from app.models.staging import (
    AuditLog,
    PurchaseRequest,
    PurchaseRequestLine,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
    UploadBatch,
)
from app.models.upload import PRLineItem, UploadMetadata
from app.models.auth import User


def persist_upload_to_db(
    db: Session,
    metadata: UploadMetadata,
    classified_items: list[dict[str, Any]],
    current_user: User,
) -> dict[str, int]:
    """
    Persist a processed upload.

    Args:
      db: SQLAlchemy session (single transaction for the whole call).
      metadata: Harry's UploadMetadata (batch_id, filename, uploader_email, ...).
      classified_items: parallel list of dicts, one per parsed line:
        [{"item": PRLineItem, "classification": {"lab_id": int|None,
                                                  "lab_group_id": int|None,
                                                  "reason": str}},
         ...]
      current_user: resolved User (via get_current_user dependency).

    Returns:
      dict with row counts: {db_batch_id, headers_inserted, lines_inserted,
                             queue_items_inserted}.

    Raises:
      HTTPException 500 if required "General" seed rows are missing.
    """
    # ─── Cache lookups for fallback values ────────────────────────────────
    general_group = (
        db.query(LabGroup).filter(LabGroup.lab_group_name == "General").first()
    )
    general_category = (
        db.query(SpendingCategory)
        .filter(SpendingCategory.category_name == "General")
        .first()
    )

    if not general_group or not general_category:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Required seed rows missing: a 'General' lab_group and a 'General' "
                "spending_category must exist. Run backend/seeds/dev_seed.sql."
            ),
        )

    # lab_group_id → that group's General lab_id (for per-group fallback)
    general_labs_by_group: dict[int, int] = {
        lab.lab_group_id: lab.lab_id
        for lab in db.query(Lab).filter(Lab.is_general.is_(True)).all()
    }
    # lowercased category_name → category_id (so we can map raw file categories)
    categories_by_name: dict[str, int] = {
        c.category_name.lower(): c.category_id for c in db.query(SpendingCategory).all()
    }

    # ─── 1. Create the upload_batches row ─────────────────────────────────
    file_ext = (
        metadata.filename.rsplit(".", 1)[-1] if "." in metadata.filename else "unknown"
    )
    batch = UploadBatch(
        uploaded_by=current_user.user_id,
        filename=metadata.filename,
        file_type=file_ext.lower()[:20],
        upload_status="review_pending",  # may flip to ready_to_commit at end
    )
    db.add(batch)
    db.flush()  # populates batch.batch_id without committing yet

    # ─── 2. Group line items by PR number ─────────────────────────────────
    items_by_pr: dict[str, list[dict[str, Any]]] = {}
    for ci in classified_items:
        items_by_pr.setdefault(ci["item"].pr_number, []).append(ci)

    headers_inserted = 0
    lines_inserted = 0
    queue_items_inserted = 0

    # ─── 3. For each unique PR: write header + its lines ──────────────────
    for pr_number, pr_items in items_by_pr.items():
        first_item: PRLineItem = pr_items[0]["item"]

        header = StagingPRHeader(
            batch_id=batch.batch_id,
            source_pr_number=pr_number,
            req_type=None,  # PRLineItem doesn't carry this; safe to leave NULL
            pr_sub_date=_parse_pr_date(first_item.pr_sub_date),
            requestor_name=first_item.requestor or None,
            purpose=first_item.purpose or None,
            grand_total_sgd=first_item.grand_total_sgd,
            wbs_code=first_item.wbs or None,
            instruction_to_vendor=first_item.instruction_to_vendor or None,
            raw_header_json=first_item.to_dict(),
        )
        db.add(header)
        db.flush()  # populates header.staging_header_id
        headers_inserted += 1

        # ─── 4. Per line: write staging line + maybe a review queue item ──
        for ci in pr_items:
            item: PRLineItem = ci["item"]
            classification: dict[str, Any] = ci["classification"]

            classifier_group_id = classification.get("lab_group_id")
            classifier_lab_id = classification.get("lab_id")
            classification_reason = classification.get("reason") or ""
            existing_final_line = _find_existing_final_line(
                db, pr_number, item.line_identity_key
            )

            # Resolve final IDs with General fallback chain
            final_group_id = classifier_group_id or general_group.lab_group_id
            final_lab_id = classifier_lab_id or general_labs_by_group.get(
                final_group_id
            )
            final_category_id = (
                categories_by_name.get((item.pr_category or "").lower())
                or general_category.category_id
            )

            # Status flags — any "General" assignment means review needed
            used_fallback_group = classifier_group_id is None
            used_fallback_lab = classifier_lab_id is None
            used_fallback_category = (
                not item.pr_category
                or item.pr_category.lower() == "general"
                or item.pr_category.lower() not in categories_by_name
            )
            if existing_final_line:
                final_lab_id = existing_final_line.lab_id
                existing_lab = _get_lab_by_id(db, final_lab_id)
                final_group_id = (
                    existing_lab.lab_group_id
                    if existing_lab is not None
                    else classifier_group_id or general_group.lab_group_id
                )
                final_category_id = (
                    existing_final_line.category_id or general_category.category_id
                )
                used_fallback_group = False
                used_fallback_lab = False
                used_fallback_category = False
                classification_reason = (
                    "Existing committed line found. Preserving reviewed "
                    "lab/category; only source status may update on commit."
                )
            any_fallback = (
                used_fallback_group or used_fallback_lab or used_fallback_category
            )

            classification_status = "unclear" if any_fallback else "confident"
            review_status = "pending_review" if any_fallback else "not_required"

            line = StagingPRLine(
                staging_header_id=header.staging_header_id,
                source_line_no=item.row_number,
                item_details=item.item_details or None,
                qty=item.quantity,
                unit_rate=item.unit_rate,
                raw_pr_category=item.pr_category or None,
                raw_lab_text=item.lab
                or None,  # Harry's resolved lab name, before review
                amount_gst=item.amount_gst,
                suggested_lab_group_id=final_group_id,
                suggested_lab_id=final_lab_id,
                suggested_category_id=final_category_id,
                classification_status=classification_status,
                duplicate_status="unchecked",
                review_status=review_status,
                match_reason=classification_reason or None,
                raw_line_json=item.to_dict(),
            )
            db.add(line)
            db.flush()  # populates line.staging_line_id
            lines_inserted += 1

            # ─── 5. Queue for review if needed ────────────────────────────
            if review_status == "pending_review":
                queue_item = ReviewQueueItem(
                    staging_line_id=line.staging_line_id,
                    queue_status="open",
                    priority="normal",
                    review_reason=classification_reason
                    or "Auto-classifier left one or more fields as General.",
                    # assigned_to_user_id stays NULL — auto-assignment is a later iteration
                )
                db.add(queue_item)
                queue_items_inserted += 1

    # ─── 6. If nothing needs review, batch is ready to commit straight ────
    if queue_items_inserted == 0:
        batch.upload_status = "ready_to_commit"

    # ─── 7. Audit: record who uploaded what, alongside the staging writes.
    db.add(
        AuditLog(
            user_id=current_user.user_id,
            action_type="UPLOAD_RECEIVED",
            entity_name="upload_batches",
            record_id=str(batch.batch_id),
            old_value=None,
            new_value={
                "filename": metadata.filename,
                "file_type": batch.file_type,
                "headers_inserted": headers_inserted,
                "lines_inserted": lines_inserted,
                "queue_items_inserted": queue_items_inserted,
                "upload_status": batch.upload_status,
            },
        )
    )

    # ─── 8. Persist everything atomically ─────────────────────────────────
    db.commit()

    return {
        "db_batch_id": batch.batch_id,
        "headers_inserted": headers_inserted,
        "lines_inserted": lines_inserted,
        "queue_items_inserted": queue_items_inserted,
    }


def _parse_pr_date(raw: str | None):
    """Best-effort parse of the PR submission date. Returns None if format is unknown."""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw, fmt).date()
        except (ValueError, TypeError):
            continue
    return None


def _find_existing_final_line(
    db: Session, source_pr_number: str, line_identity_key: str
) -> PurchaseRequestLine | None:
    if not source_pr_number or not line_identity_key:
        return None

    pr = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == source_pr_number)
        .first()
    )
    if pr is None:
        return None

    for final_line in pr.lines:
        if final_line.source_staging_line_id is None:
            continue
        staging_line = (
            db.query(StagingPRLine)
            .filter(StagingPRLine.staging_line_id == final_line.source_staging_line_id)
            .first()
        )
        if not staging_line or not isinstance(staging_line.raw_line_json, dict):
            continue
        if (
            str(staging_line.raw_line_json.get("line_identity_key", ""))
            == line_identity_key
        ):
            return final_line
    return None


def _get_lab_by_id(db: Session, lab_id: int | None) -> Lab | None:
    if lab_id is None:
        return None
    return db.query(Lab).filter(Lab.lab_id == lab_id).first()
