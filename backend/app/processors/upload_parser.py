from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import hashlib
import re
from typing import Any

import pandas as pd

from app.models.upload import PRLineItem
from app.processors.normalizer import normalize_key_part, normalize_text, parse_decimal

REQUIRED_COLUMNS = [
    "PR",
    "PR Status",
    "PR Sub Date",
    "Requestor",
    "Purpose",
    "Grand Total in SGD",
    "Item Details",
    "Qty",
    "Unit Rate",
    "WBS",
]

CRITICAL_COLUMNS = [
    "PR",
    "PR Status",
    "PR Sub Date",
    "Requestor",
    "Purpose",
    "Item Details",
]

PR_HEADER_CRITICAL_COLUMNS = [
    "PR",
    "PR Status",
    "PR Sub Date",
    "Requestor",
    "Purpose",
]

ALLOCATION_COLUMN_ALIASES = (
    "Allocatn",
    "Allocation",
    "Allocated Amount",
    "WBS Allocation",
)


def read_upload_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "csv":
        return pd.read_csv(BytesIO(content), dtype=object)
    if extension == "xlsx":
        return pd.read_excel(BytesIO(content), dtype=object)
    raise ValueError("Invalid file format. Upload a .csv or .xlsx file.")


def validate_dataframe(df: pd.DataFrame) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    normalised_columns = {normalize_text(column): column for column in df.columns}

    missing_columns = [
        column for column in REQUIRED_COLUMNS if column not in normalised_columns
    ]
    for column in missing_columns:
        errors.append(
            {
                "field": column,
                "message": "Required column is missing.",
                "severity": "error",
            }
        )

    if missing_columns:
        return errors

    active_pr_header: dict[str, Any] | None = None
    has_preceding_item_in_pr = False

    for index, row in df.iterrows():
        row_number = int(index) + 2
        if _is_completely_blank_row(row, normalised_columns):
            continue

        row_pr = normalize_text(row[normalised_columns["PR"]])
        row_item = normalize_text(row[normalised_columns["Item Details"]])

        if row_pr:
            active_pr_header = {
                col: row[normalised_columns[col]] for col in PR_HEADER_CRITICAL_COLUMNS
            }
            has_preceding_item_in_pr = False
            for column in PR_HEADER_CRITICAL_COLUMNS:
                if not normalize_text(active_pr_header[column]):
                    errors.append(
                        {
                            "field": f"Row {row_number} - {column}",
                            "message": "Critical field cannot be blank.",
                            "severity": "error",
                        }
                    )
            parsed_date = _parse_date(active_pr_header["PR Sub Date"])
            if parsed_date is None:
                errors.append(
                    {
                        "field": f"Row {row_number} - PR Sub Date",
                        "message": "Date must be a valid date.",
                        "severity": "error",
                    }
                )
        else:
            if active_pr_header is None:
                for column in PR_HEADER_CRITICAL_COLUMNS:
                    if not normalize_text(row[normalised_columns[column]]):
                        errors.append(
                            {
                                "field": f"Row {row_number} - {column}",
                                "message": "Critical field cannot be blank.",
                                "severity": "error",
                            }
                        )
                raw_date = row[normalised_columns["PR Sub Date"]]
                if _parse_date(raw_date) is None:
                    errors.append(
                        {
                            "field": f"Row {row_number} - PR Sub Date",
                            "message": "Date must be a valid date.",
                            "severity": "error",
                        }
                    )
            else:
                own_date = normalize_text(row[normalised_columns["PR Sub Date"]])
                if own_date and _parse_date(own_date) is None:
                    errors.append(
                        {
                            "field": f"Row {row_number} - PR Sub Date",
                            "message": "Date must be a valid date.",
                        }
                    )

        if row_item:
            has_preceding_item_in_pr = True
            amount = _resolve_amount(row, normalised_columns)
            if amount is None:
                errors.append(
                    {
                        "field": f"Row {row_number} - Amount",
                        "message": "Amount must be present as Amount + GST or derivable from Qty x Unit Rate.",
                        "severity": "error",
                    }
                )
        elif (
            _is_wbs_continuation_row(row, normalised_columns)
            and has_preceding_item_in_pr
        ):
            # WBS/allocation-only continuation row linked to the preceding purchase item
            continue
        else:
            errors.append(
                {
                    "field": f"Row {row_number} - Item Details",
                    "message": "Critical field cannot be blank.",
                    "severity": "error",
                }
            )
            amount = _resolve_amount(row, normalised_columns)
            if amount is None:
                errors.append(
                    {
                        "field": f"Row {row_number} - Amount",
                        "message": "Amount must be present as Amount + GST or derivable from Qty x Unit Rate.",
                        "severity": "error",
                    }
                )

    return errors


def parse_line_items(df: pd.DataFrame) -> list[PRLineItem]:
    column_map = {normalize_text(column): column for column in df.columns}
    raw_items: list[dict[str, Any]] = []
    active_header: dict[str, Any] | None = None

    for index, row in df.iterrows():
        row_number = int(index) + 2
        if _is_completely_blank_row(row, column_map):
            continue

        row_pr = normalize_text(row[column_map["PR"]])
        row_item_details = normalize_text(row[column_map["Item Details"]])

        if row_pr:
            active_header = {
                "pr_number": row_pr,
                "pr_status": normalize_text(row[column_map["PR Status"]]),
                "po_number": _optional_text(row, column_map, "PO"),
                "po_status": _optional_text(row, column_map, "PO Status"),
                "requestor": normalize_text(row[column_map["Requestor"]]),
                "purpose": normalize_text(row[column_map["Purpose"]]),
                "instruction": _optional_text(row, column_map, "Instruction to Vendor"),
                "req_type": _optional_text(row, column_map, "Req Type"),
                "pr_category": _optional_text(row, column_map, "PR Category"),
                "lab": _optional_text(row, column_map, "Lab"),
                "pr_sub_date": _format_date(row[column_map["PR Sub Date"]]),
                "grand_total": parse_decimal(row[column_map["Grand Total in SGD"]]),
                "wbs": normalize_text(row[column_map["WBS"]]),
            }

        if not row_item_details:
            if _is_wbs_continuation_row(row, column_map) and raw_items:
                amt_col = column_map.get("Amount + GST")
                row_amt_gst = parse_decimal(row[amt_col]) if amt_col else None
                raw_items[-1]["continuation_rows"].append(
                    {
                        "row_number": row_number,
                        "wbs": normalize_text(row[column_map["WBS"]]),
                        "mca": _optional_text(row, column_map, "MCA"),
                        "allocatn_raw": _optional_allocation_text(row, column_map),
                        "row_amount_gst": row_amt_gst,
                    }
                )
            continue

        hdr = active_header or {}
        pr_number = row_pr or hdr.get("pr_number", "")
        pr_status = normalize_text(row[column_map["PR Status"]]) or hdr.get(
            "pr_status", ""
        )
        po_number = _optional_text(row, column_map, "PO") or hdr.get("po_number", "")
        po_status = _optional_text(row, column_map, "PO Status") or hdr.get(
            "po_status", ""
        )
        requestor = normalize_text(row[column_map["Requestor"]]) or hdr.get(
            "requestor", ""
        )
        purpose = normalize_text(row[column_map["Purpose"]]) or hdr.get("purpose", "")
        wbs = normalize_text(row[column_map["WBS"]]) or hdr.get("wbs", "")
        instruction = _optional_text(
            row, column_map, "Instruction to Vendor"
        ) or hdr.get("instruction", "")
        req_type = _optional_text(row, column_map, "Req Type") or hdr.get(
            "req_type", ""
        )
        pr_category = _optional_text(row, column_map, "PR Category") or hdr.get(
            "pr_category", ""
        )
        lab = _optional_text(row, column_map, "Lab") or hdr.get("lab", "")
        pr_sub_date = _format_date(row[column_map["PR Sub Date"]]) or hdr.get(
            "pr_sub_date", ""
        )
        grand_total = parse_decimal(row[column_map["Grand Total in SGD"]])
        if grand_total is None:
            grand_total = hdr.get("grand_total")

        quantity = parse_decimal(row[column_map["Qty"]])
        unit_rate = parse_decimal(row[column_map["Unit Rate"]])
        amount_gst = _resolve_amount(row, column_map)

        if amount_gst is None:
            continue

        raw_items.append(
            {
                "row_number": row_number,
                "pr_number": pr_number,
                "pr_sub_date": pr_sub_date,
                "requestor": requestor,
                "purpose": purpose,
                "pr_status": pr_status,
                "po_number": po_number,
                "po_status": po_status,
                "grand_total_sgd": grand_total,
                "item_details": row_item_details,
                "quantity": quantity,
                "unit_rate": unit_rate,
                "wbs": wbs,
                "instruction_to_vendor": instruction,
                "req_type": req_type,
                "pr_category": pr_category,
                "lab": lab,
                "amount_gst": amount_gst,
                "mca": _optional_text(row, column_map, "MCA"),
                "allocatn_raw": _optional_allocation_text(row, column_map),
                "continuation_rows": [],
            }
        )

    items: list[PRLineItem] = []
    occurrence_counter: dict[tuple[str, str, str], int] = {}

    for entry in raw_items:
        occ_key = (
            normalize_key_part(entry["pr_number"]),
            normalize_key_part(entry["item_details"]),
            normalize_key_part(entry["wbs"]),
        )
        occurrence_counter[occ_key] = occurrence_counter.get(occ_key, 0) + 1
        occurrence = occurrence_counter[occ_key]

        wbs_allocations = _finalize_wbs_allocations(entry)

        identity_key = generate_line_identity_key(
            pr_number=entry["pr_number"],
            item_details=entry["item_details"],
            wbs=entry["wbs"],
            requestor=entry["requestor"],
            purpose=entry["purpose"],
            item_occurrence=occurrence,
        )

        hash_fields: dict[str, str] = {
            "pr_number": entry["pr_number"],
            "pr_status": entry["pr_status"],
            "po_number": entry["po_number"],
            "po_status": entry["po_status"],
            "pr_sub_date": entry["pr_sub_date"],
            "requestor": entry["requestor"],
            "purpose": entry["purpose"],
            "grand_total_sgd": _decimal_to_text(entry["grand_total_sgd"]),
            "item_details": entry["item_details"],
            "quantity": _decimal_to_text(entry["quantity"]),
            "unit_rate": _decimal_to_text(entry["unit_rate"]),
            "wbs": entry["wbs"],
            "instruction_to_vendor": entry["instruction_to_vendor"],
            "req_type": entry["req_type"],
            "pr_category": entry["pr_category"],
            "lab": entry["lab"],
            "amount_gst": _decimal_to_text(entry["amount_gst"]),
        }
        if wbs_allocations:
            hash_fields["wbs_allocations"] = "|".join(
                f"{a.get('wbs', '')}={a.get('amount_gst', '')}" for a in wbs_allocations
            )

        content_hash = generate_content_hash(hash_fields)

        items.append(
            PRLineItem(
                row_number=entry["row_number"],
                pr_number=entry["pr_number"],
                pr_sub_date=entry["pr_sub_date"],
                requestor=entry["requestor"],
                purpose=entry["purpose"],
                pr_status=entry["pr_status"],
                po_number=entry["po_number"],
                po_status=entry["po_status"],
                grand_total_sgd=entry["grand_total_sgd"],
                item_details=entry["item_details"],
                quantity=entry["quantity"],
                unit_rate=entry["unit_rate"],
                wbs=entry["wbs"],
                instruction_to_vendor=entry["instruction_to_vendor"],
                req_type=entry["req_type"],
                pr_category=entry["pr_category"],
                lab=entry["lab"],
                amount_gst=entry["amount_gst"],
                line_identity_key=identity_key,
                content_hash=content_hash,
                wbs_allocations=wbs_allocations,
            )
        )

    return items


def generate_line_identity_key(
    *,
    pr_number: str,
    item_details: str,
    wbs: str,
    requestor: str,
    purpose: str,
    item_occurrence: int = 1,
) -> str:
    parts = [
        normalize_key_part(pr_number),
        normalize_key_part(item_details),
        normalize_key_part(wbs),
        normalize_key_part(requestor),
        normalize_key_part(purpose),
    ]
    if item_occurrence > 1:
        parts.append(f"occ:{item_occurrence}")
    raw_key = "|".join(parts)
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_content_hash(fields: dict[str, str]) -> str:
    raw_content = "|".join(
        f"{key}={normalize_key_part(value)}" for key, value in sorted(fields.items())
    )
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


def _compute_allocation_portion_amount(
    raw_alloc_text: str,
    raw_row_amount_gst: Decimal | None,
    mca_mode: str,
    parent_unit_rate: Decimal | None,
) -> tuple[Decimal | None, Decimal | None]:
    """
    Returns (allocated_amount_sgd, allocated_quantity).
    - When MCA is 'Quantity', raw_alloc_text is a unit count and dollar amount = count * unit_rate.
    - When MCA is 'Amount' (or blank/NA with an explicit allocation value), raw_alloc_text is the dollar amount.
    - Falls back to raw_row_amount_gst if provided on a continuation row without an Allocatn column.
    """
    alloc_val = parse_decimal(raw_alloc_text)
    mca_clean = (mca_mode or "").strip().lower()
    if alloc_val is not None:
        if mca_clean == "quantity":
            if parent_unit_rate is not None:
                return (
                    (alloc_val * parent_unit_rate).quantize(Decimal("0.01")),
                    alloc_val,
                )
            return None, alloc_val
        return alloc_val.quantize(Decimal("0.01")), None
    if raw_row_amount_gst is not None:
        return raw_row_amount_gst.quantize(Decimal("0.01")), None
    return None, None


def _split_inline_wbs_codes(wbs_text: str) -> list[str]:
    if not wbs_text or not wbs_text.strip():
        return []
    parts = [tok.strip() for tok in re.split(r"[,;/&]+", wbs_text) if tok.strip()]
    seen: list[str] = []
    for part in parts:
        if part.upper() not in {s.upper() for s in seen}:
            seen.append(part)
    return seen


def _finalize_wbs_allocations(
    parent_entry: dict[str, Any],
) -> tuple[dict[str, Any], ...]:
    """
    Evaluates the parent item and any attached WBS/allocation continuation rows:
      - If there are no continuation rows and only one WBS code, returns ().
      - If continuation rows exist and all rows reuse the exact same WBS as the parent
        item AND their amounts reconcile with the parent item's amount_gst (e.g. MCA=Quantity
        same-WBS unit rows), collapses them into () so the item stays a single-WBS line.
      - If continuation rows introduce a different secondary WBS, or have missing/mismatched
        allocation amounts, returns the tuple of exact WBS allocation dicts.
    """
    continuations: list[dict[str, Any]] = parent_entry["continuation_rows"]
    parent_wbs = parent_entry["wbs"]
    parent_mca = parent_entry["mca"]
    parent_rate = parent_entry["unit_rate"]
    line_amount = parent_entry["amount_gst"]

    if not continuations:
        inline_codes = _split_inline_wbs_codes(parent_wbs)
        if len(inline_codes) > 1:
            return tuple(
                {
                    "row_number": parent_entry["row_number"],
                    "wbs": code,
                    "mca": parent_mca or "Amount",
                    "raw_allocation": None,
                    "quantity": None,
                    "amount_gst": None,
                    "amount_missing": True,
                }
                for code in inline_codes
            )
        return ()

    first_amt, first_qty = _compute_allocation_portion_amount(
        parent_entry["allocatn_raw"],
        None,
        parent_mca,
        parent_rate,
    )

    alloc_entries: list[dict[str, Any]] = [
        {
            "row_number": parent_entry["row_number"],
            "wbs": parent_wbs,
            "mca": parent_mca or "Amount",
            "raw_allocation": parent_entry["allocatn_raw"] or None,
            "quantity": str(first_qty) if first_qty is not None else None,
            "amount_gst": str(first_amt) if first_amt is not None else None,
            "amount_missing": first_amt is None,
        }
    ]

    for cont in continuations:
        cont_wbs = cont["wbs"] or parent_wbs
        cont_mca = cont["mca"] or parent_mca or "Amount"
        cont_amt, cont_qty = _compute_allocation_portion_amount(
            cont["allocatn_raw"],
            cont["row_amount_gst"],
            cont_mca,
            parent_rate,
        )
        alloc_entries.append(
            {
                "row_number": cont["row_number"],
                "wbs": cont_wbs,
                "mca": cont_mca,
                "raw_allocation": cont["allocatn_raw"] or None,
                "quantity": str(cont_qty) if cont_qty is not None else None,
                "amount_gst": str(cont_amt) if cont_amt is not None else None,
                "amount_missing": cont_amt is None,
            }
        )

    distinct_wbs = {
        (entry["wbs"] or "").strip().upper()
        for entry in alloc_entries
        if (entry["wbs"] or "").strip()
    }
    any_missing = any(entry["amount_missing"] for entry in alloc_entries)
    total_allocated = sum(
        (
            Decimal(entry["amount_gst"])
            for entry in alloc_entries
            if entry["amount_gst"] is not None
        ),
        Decimal("0.00"),
    )
    reconciles = (
        not any_missing
        and line_amount is not None
        and abs(total_allocated - line_amount.quantize(Decimal("0.01")))
        <= Decimal("0.01")
    )

    if len(distinct_wbs) <= 1 and reconciles:
        return ()

    return tuple(alloc_entries)


def _format_date(value: object) -> str:
    parsed = _parse_date(value)
    return "" if parsed is None else parsed.isoformat()


def _parse_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = normalize_text(value)
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d/%m/%y", "%d-%m-%Y", "%d-%m-%y"):
        if _matches_date_format(text, fmt):
            try:
                return datetime.strptime(text, fmt).date()
            except ValueError:
                pass
    parsed = pd.to_datetime(text, errors="coerce", dayfirst=True)
    if pd.isna(parsed):
        return None
    return parsed.date()


def _decimal_to_text(value: Decimal | None) -> str:
    return "" if value is None else str(value)


def _matches_date_format(text: str, fmt: str) -> bool:
    patterns = {
        "%Y-%m-%d": r"^\d{4}-\d{1,2}-\d{1,2}$",
        "%d/%m/%Y": r"^\d{1,2}/\d{1,2}/\d{4}$",
        "%d/%m/%y": r"^\d{1,2}/\d{1,2}/\d{2}$",
        "%d-%m-%Y": r"^\d{1,2}-\d{1,2}-\d{4}$",
        "%d-%m-%y": r"^\d{1,2}-\d{1,2}-\d{2}$",
    }
    return re.match(patterns[fmt], text) is not None


def _optional_text(
    row: pd.Series,
    column_map: dict[str, str],
    column_name: str,
) -> str:
    source_column = column_map.get(column_name)
    if source_column is None:
        return ""
    return normalize_text(row[source_column])


def _optional_allocation_text(
    row: pd.Series,
    column_map: dict[str, str],
) -> str:
    for alias in ALLOCATION_COLUMN_ALIASES:
        val = _optional_text(row, column_map, alias)
        if val:
            return val
    return ""


def _is_wbs_continuation_row(
    row: pd.Series,
    column_map: dict[str, str],
) -> bool:
    pr_number = _optional_text(row, column_map, "PR")
    item_details = _optional_text(row, column_map, "Item Details")
    if pr_number or item_details:
        return False

    wbs = _optional_text(row, column_map, "WBS")
    alloc = _optional_allocation_text(row, column_map)
    amt_col = column_map.get("Amount + GST")
    amt_text = normalize_text(row[amt_col]) if amt_col else ""
    return bool(wbs or alloc or amt_text)


def _is_completely_blank_row(
    row: pd.Series,
    column_map: dict[str, str],
) -> bool:
    return all(not normalize_text(row[col]) for col in column_map.values())


def _resolve_amount(
    row: pd.Series,
    column_map: dict[str, str],
) -> Decimal | None:
    amount_column = column_map.get("Amount + GST")
    if amount_column is not None:
        amount = parse_decimal(row[amount_column])
        if amount is not None:
            return amount

    quantity = parse_decimal(row[column_map["Qty"]])
    unit_rate = parse_decimal(row[column_map["Unit Rate"]])
    if quantity is None or unit_rate is None:
        return None
    return quantity * unit_rate
