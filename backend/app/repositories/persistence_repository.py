"""
Persistence layer for upload pipeline.

Takes the output of Harry's parser + classifier and writes it to:
  - upload_batches        (1 row per upload)
  - staging_pr_headers    (1 row per unique PR number in the file)
  - staging_pr_lines      (1 row per parsed line, or X split rows when multiple labs are detected)
  - review_queue_items    (1 row per line that needs human review)
  - audit_logs            (1 row per upload, action_type='UPLOAD_RECEIVED')

Everything happens in a single transaction. If any insert fails,
SQLAlchemy rolls back the whole batch (via the session lifecycle in get_db).
"""

from datetime import date, datetime
from decimal import Decimal, ROUND_DOWN
import re
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session, joinedload

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

    general_labs_by_group: dict[int, int] = {
        lab.lab_group_id: lab.lab_id
        for lab in db.query(Lab).filter(Lab.is_general.is_(True)).all()
    }

    categories_by_name: dict[str, int] = {
        cat.category_name.strip().lower(): cat.category_id
        for cat in db.query(SpendingCategory).all()
        if cat.category_name
    }

    # Pre-load all non-General labs (with aliases) for multi-lab detection
    candidate_labs: list[Lab] = (
        db.query(Lab)
        .options(joinedload(Lab.aliases))
        .filter(Lab.is_general.is_(False))
        .all()
    )
    lab_patterns = _build_lab_matcher_patterns(candidate_labs)

    # ─── 1. Create the upload_batches row ─────────────────────────────────
    file_ext = (
        metadata.filename.rsplit(".", 1)[-1] if "." in metadata.filename else "unknown"
    )
    batch = UploadBatch(
        uploaded_by=current_user.user_id,
        filename=metadata.filename,
        file_type=file_ext.lower()[:20],
        upload_status="review_pending",
    )
    db.add(batch)
    db.flush()

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
            req_type=first_item.req_type,
            pr_sub_date=_parse_pr_date(first_item.pr_sub_date),
            requestor_name=first_item.requestor or None,
            purpose=first_item.purpose or None,
            grand_total_sgd=first_item.grand_total_sgd,
            wbs_code=first_item.wbs or None,
            instruction_to_vendor=first_item.instruction_to_vendor or None,
            raw_header_json=first_item.to_dict(),
        )
        db.add(header)
        db.flush()
        headers_inserted += 1

        # ─── 4. Per line: detect single vs. multi-lab distribution ────────
        for ci in pr_items:
            item: PRLineItem = ci["item"]
            classification: dict[str, Any] = ci["classification"]

            detected_labs = _detect_labs_in_line(item, lab_patterns, first_item)
            line_total_amount = _resolve_line_amount(item)

            # Resolve category from classifier or directly from Req Type / PR Category
            classifier_category_id = classification.get("category_id")
            if (
                classifier_category_id is None
                or classifier_category_id == general_category.category_id
            ):
                matched_cat_id = _match_category_id(
                    item, categories_by_name, general_category.category_id
                )
                if matched_cat_id is not None:
                    classifier_category_id = matched_cat_id

            # ─── 4A. Automated Multi-Lab Spending Distribution ────────────
            if len(detected_labs) > 1:
                num_labs = len(detected_labs)
                amount_shares = _split_amount_equally(line_total_amount, num_labs)
                qty_shares = (
                    _split_quantity_equally(item.quantity, num_labs)
                    if item.quantity is not None
                    else [None] * num_labs
                )
                detected_labels = ", ".join(
                    lab.lab_code or lab.lab_name for lab in detected_labs
                )

                for idx, target_lab in enumerate(detected_labs):
                    split_identity_key = (
                        f"{item.line_identity_key}::lab_{target_lab.lab_id}"
                        if item.line_identity_key
                        else f"{pr_number}::{item.row_number}::lab_{target_lab.lab_id}"
                    )
                    existing_final_line = _find_existing_final_line(
                        db, pr_number, split_identity_key
                    )

                    final_lab_id = target_lab.lab_id
                    final_group_id = (
                        target_lab.lab_group_id
                        or classification.get("lab_group_id")
                        or general_group.lab_group_id
                    )
                    final_category_id = (
                        classifier_category_id or general_category.category_id
                    )

                    used_fallback_group = final_group_id == general_group.lab_group_id
                    used_fallback_lab = False
                    used_fallback_category = (
                        final_category_id == general_category.category_id
                    )

                    split_reason = (
                        f"Automated multi-lab spending distribution ({idx + 1}/{num_labs} "
                        f"equal share across: {detected_labels})."
                    )

                    if existing_final_line:
                        final_lab_id = existing_final_line.lab_id
                        existing_lab = _get_lab_by_id(db, final_lab_id)
                        final_group_id = (
                            existing_lab.lab_group_id
                            if existing_lab is not None
                            else final_group_id
                        )
                        final_category_id = (
                            existing_final_line.category_id
                            or general_category.category_id
                        )
                        used_fallback_group = False
                        used_fallback_lab = False
                        used_fallback_category = False
                        split_reason = (
                            "Existing committed split line found. Preserving reviewed "
                            "lab/category; only source status may update on commit."
                        )

                    any_fallback = (
                        used_fallback_group
                        or used_fallback_lab
                        or used_fallback_category
                    )
                    classification_status = "unclear" if any_fallback else "confident"
                    review_status = "pending_review" if any_fallback else "not_required"

                    raw_json = dict(item.to_dict())
                    raw_json["line_identity_key"] = split_identity_key
                    raw_json["split_lab_count"] = num_labs
                    raw_json["split_index"] = idx + 1
                    raw_json["split_target_lab_id"] = target_lab.lab_id
                    raw_json["original_amount_gst"] = str(line_total_amount)
                    raw_json["amount_gst"] = str(amount_shares[idx])

                    base_details = item.item_details or "Collective Purchase"
                    lab_tag = target_lab.lab_code or target_lab.lab_name
                    split_item_details = (
                        f"{base_details} [{lab_tag} — 1/{num_labs} share]"
                    )

                    line = StagingPRLine(
                        staging_header_id=header.staging_header_id,
                        source_line_no=item.row_number,
                        item_details=split_item_details,
                        qty=qty_shares[idx],
                        unit_rate=item.unit_rate,
                        raw_pr_category=item.pr_category or item.req_type or None,
                        raw_lab_text=target_lab.lab_code
                        or target_lab.lab_name
                        or item.lab
                        or item.purpose
                        or None,
                        amount_gst=amount_shares[idx],
                        suggested_lab_group_id=final_group_id,
                        suggested_lab_id=final_lab_id,
                        suggested_category_id=final_category_id,
                        classification_status=classification_status,
                        duplicate_status="unchecked",
                        review_status=review_status,
                        match_reason=split_reason,
                        raw_line_json=raw_json,
                    )
                    db.add(line)
                    db.flush()
                    lines_inserted += 1

                    if review_status == "pending_review":
                        queue_item = ReviewQueueItem(
                            staging_line_id=line.staging_line_id,
                            queue_status="open",
                            priority="normal",
                            review_reason=(
                                f"{split_reason} Category or Lab Group still requires review."
                            ),
                        )
                        db.add(queue_item)
                        queue_items_inserted += 1

                continue

            # ─── 4B. Standard Single-Lab Line Processing ──────────────────
            classifier_group_id = classification.get("lab_group_id")
            classifier_lab_id = classification.get("lab_id")

            if classifier_lab_id is None and len(detected_labs) == 1:
                classifier_lab_id = detected_labs[0].lab_id
                if classifier_group_id is None:
                    classifier_group_id = detected_labs[0].lab_group_id

            classification_reason = classification.get("reason") or ""
            existing_final_line = _find_existing_final_line(
                db, pr_number, item.line_identity_key
            )

            # Resolve final IDs with General fallback chain
            final_group_id = classifier_group_id or general_group.lab_group_id
            final_lab_id = classifier_lab_id or general_labs_by_group.get(
                final_group_id
            )
            final_category_id = classifier_category_id or general_category.category_id

            used_fallback_group = classifier_group_id is None
            used_fallback_lab = classifier_lab_id is None
            used_fallback_category = classifier_category_id is None

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
                raw_pr_category=item.pr_category or item.req_type or None,
                raw_lab_text=item.lab or item.purpose or None,
                amount_gst=line_total_amount,
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
            db.flush()
            lines_inserted += 1

            # ─── 5. Queue for review if needed ────────────────────────────
            if review_status == "pending_review":
                queue_item = ReviewQueueItem(
                    staging_line_id=line.staging_line_id,
                    queue_status="open",
                    priority="normal",
                    review_reason=classification_reason
                    or "Auto-classifier left one or more fields as General.",
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


# ─── Multi-Lab Detection & Equal Spending Split Helpers ──────────────────
def _expand_shorthand_lab_codes(text: str) -> str:
    """
    Expands shorthand lab code lists sharing a block-level prefix, e.g.:
      'E2-02-01/02/03' -> 'E2-02-01, E2-02-02, E2-02-03'
      'E2-02-02 & 14'  -> 'E2-02-02, E2-02-14'
    """
    pattern = re.compile(
        r"\b([A-Za-z]\d+-\d+-)([A-Za-z0-9]{1,4})((?:\s*(?:/|,|&|\band\b)\s*[A-Za-z0-9]{1,4}(?![A-Za-z0-9-]))+)",
        re.IGNORECASE,
    )

    def repl(match: re.Match[str]) -> str:
        prefix = match.group(1)
        first_room = match.group(2)
        rest = match.group(3)
        extra_rooms = [
            tok.strip()
            for tok in re.split(r"(?:/|,|&|\band\b)", rest, flags=re.IGNORECASE)
            if tok.strip()
        ]
        all_codes = [f"{prefix}{first_room}"] + [f"{prefix}{r}" for r in extra_rooms]
        return ", ".join(all_codes)

    return pattern.sub(repl, text)


def _build_lab_matcher_patterns(
    labs: list[Lab],
) -> list[tuple[str, re.Pattern[str], Lab]]:
    """
    Build compiled regex patterns for every active non-General lab from its
    lab_code, auto-generated SIT code variants (E2L2R02, E2-L2-02, E2L202),
    lab_name, stripped base name, venue tags, and lab_aliases.
    Sorted longest-first so specific names win over shorter substrings.
    """
    code_regex = re.compile(r"^([A-Z]\d+)-(\d+)-([A-Z0-9]+)$", re.IGNORECASE)
    raw_entries: list[tuple[str, Lab]] = []

    for lab in labs:
        tokens: set[str] = set()
        code = (lab.lab_code or "").strip()
        name = (lab.lab_name or "").strip()

        if len(code) >= 2:
            tokens.add(code)
            match = code_regex.match(code)
            if match:
                block = match.group(1).upper()
                level_short = str(int(match.group(2)))
                room = match.group(3).upper()
                tokens.add(f"{block}L{level_short}R{room}")
                tokens.add(f"{block}-L{level_short}-{room}")
                tokens.add(f"{block}L{level_short}{room}")

        if len(name) >= 3:
            tokens.add(name)
            if name.lower().endswith(" lab"):
                short_name = name[:-4].strip()
                if len(short_name) >= 3 and short_name.lower() != "general":
                    tokens.add(short_name)

        if lab.venue:
            for tag in lab.venue.split(","):
                clean_tag = tag.strip()
                if len(clean_tag) >= 3 and clean_tag.lower() != "general":
                    tokens.add(clean_tag)

        for alias in getattr(lab, "aliases", []) or []:
            if alias.alias_text and len(alias.alias_text.strip()) >= 2:
                tokens.add(alias.alias_text.strip())

        for token in tokens:
            raw_entries.append((token, lab))

    raw_entries.sort(key=lambda pair: len(pair[0]), reverse=True)

    compiled: list[tuple[str, re.Pattern[str], Lab]] = []
    for token, lab in raw_entries:
        pattern = re.compile(
            rf"(?<![A-Za-z0-9]){re.escape(token)}(?![A-Za-z0-9])",
            re.IGNORECASE,
        )
        compiled.append((token, pattern, lab))
    return compiled


def _find_labs_in_text(
    text: str, lab_patterns: list[tuple[str, re.Pattern[str], Lab]]
) -> list[Lab]:
    """
    Return distinct Lab objects mentioned in `text`, ordered by their first
    appearance in the string and guarded against overlapping substring matches.
    """
    if not text or not text.strip():
        return []

    expanded_text = _expand_shorthand_lab_codes(text)
    occupied_spans: list[tuple[int, int]] = []
    matches_with_pos: list[tuple[int, Lab]] = []
    seen_lab_ids: set[int] = set()

    for _, pattern, lab in lab_patterns:
        for match in pattern.finditer(expanded_text):
            start, end = match.span()
            if any(
                not (end <= occ_start or start >= occ_end)
                for occ_start, occ_end in occupied_spans
            ):
                continue
            occupied_spans.append((start, end))
            if lab.lab_id not in seen_lab_ids:
                seen_lab_ids.add(lab.lab_id)
                matches_with_pos.append((start, lab))

    matches_with_pos.sort(key=lambda item: item[0])
    return [lab for _, lab in matches_with_pos]


def _detect_labs_in_line(
    item: PRLineItem,
    lab_patterns: list[tuple[str, re.Pattern[str], Lab]],
    header_item: PRLineItem | None = None,
) -> list[Lab]:
    """
    Detect labs referenced on a PR line:
      1. Checks explicit location/purpose fields (`lab`, `purpose`, `instruction_to_vendor`).
         If >= 2 labs are found there, returns them directly.
      2. Checks `item_details` for collective multi-lab purchases. If `item_details`
         itself references >= 2 labs, merges them with any location field lab.
      3. Falls back to header-level `purpose` / `instruction_to_vendor` on multi-row PRs.
    """
    loc_text = " | ".join(
        part
        for part in (item.lab, item.purpose, item.instruction_to_vendor)
        if part and str(part).strip()
    )
    loc_labs = _find_labs_in_text(loc_text, lab_patterns)
    if len(loc_labs) >= 2:
        return loc_labs

    details_labs = _find_labs_in_text(item.item_details or "", lab_patterns)
    if len(details_labs) >= 2:
        seen = {lab.lab_id for lab in loc_labs}
        merged = list(loc_labs)
        for lab in details_labs:
            if lab.lab_id not in seen:
                seen.add(lab.lab_id)
                merged.append(lab)
        return merged

    if header_item is not None and header_item is not item:
        header_loc_text = " | ".join(
            part
            for part in (
                loc_text,
                header_item.purpose,
                header_item.instruction_to_vendor,
            )
            if part and str(part).strip()
        )
        header_detected = _find_labs_in_text(header_loc_text, lab_patterns)
        if len(header_detected) >= 2:
            return header_detected

    return loc_labs or details_labs


def _resolve_line_amount(item: PRLineItem) -> Decimal:
    """
    Resolve the total SGD spend for a PR line, falling back to Qty * Unit Rate
    or Grand Total in SGD if `amount_gst` is not populated.
    """
    if item.amount_gst is not None:
        amt = Decimal(str(item.amount_gst))
        if amt > 0:
            return amt.quantize(Decimal("0.01"))
    if item.quantity is not None and item.unit_rate is not None:
        calc = Decimal(str(item.quantity)) * Decimal(str(item.unit_rate))
        if calc > 0:
            return calc.quantize(Decimal("0.01"))
    if item.grand_total_sgd is not None:
        return Decimal(str(item.grand_total_sgd)).quantize(Decimal("0.01"))
    return Decimal("0.00")


def _match_category_id(
    item: PRLineItem,
    categories_by_name: dict[str, int],
    general_cat_id: int,
) -> int | None:
    """
    Match `item.req_type` (Column 8 in DivPRReport, e.g. 'Maintenance') or
    `item.pr_category` against configured SpendingCategory names.
    """
    for raw_val in (item.pr_category, item.req_type):
        if not raw_val or not str(raw_val).strip():
            continue
        cleaned = str(raw_val).strip().lower()
        if (
            cleaned in categories_by_name
            and categories_by_name[cleaned] != general_cat_id
        ):
            return categories_by_name[cleaned]
        for cat_name, cat_id in categories_by_name.items():
            if cat_id != general_cat_id and (
                cat_name in cleaned or cleaned in cat_name
            ):
                return cat_id
    return None


def _split_amount_equally(total: Any, count: int) -> list[Decimal]:
    """
    Divide `total` across `count` labs in 2-decimal currency math.
    Any $0.01 rounding remainder is distributed across the first shares so
    `sum(shares) == total` down to the cent.
    """
    if count <= 0:
        return [Decimal("0.00")]
    if total is None:
        return [Decimal("0.00")] * count

    total_dec = Decimal(str(total)).quantize(Decimal("0.01"))
    base_share = (total_dec / Decimal(count)).quantize(
        Decimal("0.01"), rounding=ROUND_DOWN
    )
    remainder_cents = int(
        ((total_dec - (base_share * count)) * 100).to_integral_value()
    )
    return [
        base_share + (Decimal("0.01") if i < remainder_cents else Decimal("0.00"))
        for i in range(count)
    ]


def _split_quantity_equally(qty: Any, count: int) -> list[Decimal | None]:
    if qty is None or count <= 0:
        return [None] * max(count, 1)
    qty_dec = Decimal(str(qty))
    share = (qty_dec / Decimal(count)).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
    remainder = (qty_dec - (share * count)).quantize(Decimal("0.01"))
    return [share + (remainder if i == 0 else Decimal("0.00")) for i in range(count)]


def _parse_pr_date(raw: Any):
    if not raw:
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    raw_str = str(raw).strip().split(" ")[0].split("T")[0]
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"):
        try:
            return datetime.strptime(raw_str, fmt).date()
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
