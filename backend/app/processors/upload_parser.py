from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
import hashlib

import pandas as pd

from app.models.upload import PRLineItem
from app.processors.normalizer import normalize_key_part, normalize_text, parse_decimal

REQUIRED_COLUMNS = [
    "PR",
    "PR Sub Date",
    "Requestor",
    "Purpose",
    "Grand Total in SGD",
    "Item Details",
    "Qty",
    "Unit Rate",
    "WBS",
    "Instruction to Vendor",
    "PR Category",
    "Lab",
    "Amount + GST",
]

CRITICAL_COLUMNS = [
    "PR",
    "PR Sub Date",
    "Requestor",
    "Purpose",
    "Item Details",
    "WBS",
    "Amount + GST",
]


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

    for index, row in df.iterrows():
        row_number = int(index) + 2
        for column in CRITICAL_COLUMNS:
            if not normalize_text(row[normalised_columns[column]]):
                errors.append(
                    {
                        "field": f"Row {row_number} - {column}",
                        "message": "Critical field cannot be blank.",
                        "severity": "error",
                    }
                )

        amount = parse_decimal(row[normalised_columns["Amount + GST"]])
        if amount is None:
            errors.append(
                {
                    "field": f"Row {row_number} - Amount + GST",
                    "message": "Amount must be a valid number.",
                    "severity": "error",
                }
            )

        parsed_date = _parse_date(row[normalised_columns["PR Sub Date"]])
        if parsed_date is None:
            errors.append(
                {
                    "field": f"Row {row_number} - PR Sub Date",
                    "message": "Date must be a valid date.",
                    "severity": "error",
                }
            )

    return errors


def parse_line_items(df: pd.DataFrame) -> list[PRLineItem]:
    column_map = {normalize_text(column): column for column in df.columns}
    items: list[PRLineItem] = []

    for index, row in df.iterrows():
        row_number = int(index) + 2
        pr_number = normalize_text(row[column_map["PR"]])
        requestor = normalize_text(row[column_map["Requestor"]])
        purpose = normalize_text(row[column_map["Purpose"]])
        item_details = normalize_text(row[column_map["Item Details"]])
        wbs = normalize_text(row[column_map["WBS"]])
        instruction = normalize_text(row[column_map["Instruction to Vendor"]])
        pr_category = normalize_text(row[column_map["PR Category"]])
        lab = normalize_text(row[column_map["Lab"]])
        pr_sub_date = _format_date(row[column_map["PR Sub Date"]])
        grand_total = parse_decimal(row[column_map["Grand Total in SGD"]])
        quantity = parse_decimal(row[column_map["Qty"]])
        unit_rate = parse_decimal(row[column_map["Unit Rate"]])
        amount_gst = parse_decimal(row[column_map["Amount + GST"]])

        if amount_gst is None:
            continue

        identity_key = generate_line_identity_key(
            pr_number=pr_number,
            item_details=item_details,
            wbs=wbs,
            requestor=requestor,
            purpose=purpose,
        )
        content_hash = generate_content_hash(
            {
                "pr_number": pr_number,
                "pr_sub_date": pr_sub_date,
                "requestor": requestor,
                "purpose": purpose,
                "grand_total_sgd": _decimal_to_text(grand_total),
                "item_details": item_details,
                "quantity": _decimal_to_text(quantity),
                "unit_rate": _decimal_to_text(unit_rate),
                "wbs": wbs,
                "instruction_to_vendor": instruction,
                "pr_category": pr_category,
                "lab": lab,
                "amount_gst": _decimal_to_text(amount_gst),
            }
        )

        items.append(
            PRLineItem(
                row_number=row_number,
                pr_number=pr_number,
                pr_sub_date=pr_sub_date,
                requestor=requestor,
                purpose=purpose,
                grand_total_sgd=grand_total,
                item_details=item_details,
                quantity=quantity,
                unit_rate=unit_rate,
                wbs=wbs,
                instruction_to_vendor=instruction,
                pr_category=pr_category,
                lab=lab,
                amount_gst=amount_gst,
                line_identity_key=identity_key,
                content_hash=content_hash,
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
) -> str:
    raw_key = "|".join(
        [
            normalize_key_part(pr_number),
            normalize_key_part(item_details),
            normalize_key_part(wbs),
            normalize_key_part(requestor),
            normalize_key_part(purpose),
        ]
    )
    return hashlib.sha256(raw_key.encode("utf-8")).hexdigest()


def generate_content_hash(fields: dict[str, str]) -> str:
    raw_content = "|".join(
        f"{key}={normalize_key_part(value)}" for key, value in sorted(fields.items())
    )
    return hashlib.sha256(raw_content.encode("utf-8")).hexdigest()


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
    parsed = pd.to_datetime(text, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _decimal_to_text(value: Decimal | None) -> str:
    return "" if value is None else str(value)
