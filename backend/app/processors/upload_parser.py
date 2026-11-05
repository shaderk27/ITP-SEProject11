from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from html.parser import HTMLParser
from io import BytesIO
from zipfile import BadZipFile, ZIP_DEFLATED, ZipFile
import hashlib
import re

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

PR_LEVEL_COLUMNS = [
    "PR",
    "PO",
    "PR Status",
    "PO Status",
    "PR Sub Date",
    "Requestor",
    "Purpose",
    "Grand Total in SGD",
    "Req Type",
    "PR Category",
]

_STRICT_OPEN_XML_NAMESPACES = {
    b"http://purl.oclc.org/ooxml/spreadsheetml/main": (
        b"http://schemas.openxmlformats.org/spreadsheetml/2006/main"
    ),
    b"http://purl.oclc.org/ooxml/officeDocument/relationships": (
        b"http://schemas.openxmlformats.org/officeDocument/2006/relationships"
    ),
}


class _HtmlTableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell_parts: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"td", "th"} and self._row is not None:
            self._cell_parts = []

    def handle_data(self, data: str) -> None:
        if self._cell_parts is not None:
            self._cell_parts.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"td", "th"} and self._cell_parts is not None:
            if self._row is not None:
                self._row.append("".join(self._cell_parts).strip())
            self._cell_parts = None
        elif tag.lower() == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None


def read_upload_dataframe(filename: str, content: bytes) -> pd.DataFrame:
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension == "csv":
        dataframe = pd.read_csv(BytesIO(content), dtype=object)
    elif extension == "xls":
        dataframe = _read_legacy_xls(content)
    if extension == "xlsx":
        dataframe = pd.read_excel(_normalise_strict_xlsx(content), dtype=object)
    elif extension not in {"csv", "xls"}:
        raise ValueError("Invalid file format. Upload a .csv, .xls, or .xlsx file.")

    return _prepare_source_rows(dataframe)


def _read_legacy_xls(content: bytes) -> pd.DataFrame:
    text = _decode_html_xls(content)
    if text is None:
        return pd.read_excel(BytesIO(content), dtype=object, engine="xlrd")

    parser = _HtmlTableParser()
    parser.feed(text)
    if len(parser.rows) < 2:
        raise ValueError("The .xls HTML export does not contain a data table.")

    headers = parser.rows[0]
    width = len(headers)
    rows = [row[:width] + [""] * max(0, width - len(row)) for row in parser.rows[1:]]
    return pd.DataFrame(rows, columns=headers, dtype=object)


def _decode_html_xls(content: bytes) -> str | None:
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        text = content.decode("utf-16")
    else:
        sample = content[:512].lstrip().lower()
        if not sample.startswith((b"<table", b"<html", b"<!doctype")):
            return None
        text = content.decode("utf-8-sig")

    lowered = text.lstrip().lower()
    return text if lowered.startswith(("<table", "<html", "<!doctype")) else None


def _normalise_strict_xlsx(content: bytes) -> BytesIO:
    """Convert Strict Open XML namespaces for openpyxl without changing the upload."""
    source = BytesIO(content)
    try:
        with ZipFile(source) as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            if not any(uri in workbook_xml for uri in _STRICT_OPEN_XML_NAMESPACES):
                source.seek(0)
                return source

            converted = BytesIO()
            with ZipFile(converted, "w", ZIP_DEFLATED) as output:
                for member in archive.infolist():
                    data = archive.read(member.filename)
                    if member.filename.endswith((".xml", ".rels")):
                        for (
                            strict_uri,
                            standard_uri,
                        ) in _STRICT_OPEN_XML_NAMESPACES.items():
                            data = data.replace(strict_uri, standard_uri)
                    output.writestr(member, data)
            converted.seek(0)
            return converted
    except (BadZipFile, KeyError) as error:
        raise ValueError("The .xlsx file is not a valid Excel workbook.") from error


def _prepare_source_rows(dataframe: pd.DataFrame) -> pd.DataFrame:
    """Remove export formatting rows and expand merged PR headers over line items."""
    normalised_columns = {
        normalize_text(column): column for column in dataframe.columns
    }
    item_column = normalised_columns.get("Item Details")
    quantity_column = normalised_columns.get("Qty")
    rate_column = normalised_columns.get("Unit Rate")
    amount_column = normalised_columns.get("Amount + GST")

    line_columns = [
        column
        for column in (item_column, quantity_column, rate_column, amount_column)
        if column is not None
    ]
    if line_columns:
        meaningful_line = (
            dataframe[line_columns]
            .apply(lambda column: column.map(lambda value: bool(normalize_text(value))))
            .any(axis=1)
        )
        dataframe = dataframe.loc[meaningful_line].copy()

    columns_to_fill = [
        normalised_columns[column]
        for column in PR_LEVEL_COLUMNS
        if column in normalised_columns
    ]
    if columns_to_fill:
        with pd.option_context("future.no_silent_downcasting", True):
            dataframe[columns_to_fill] = (
                dataframe[columns_to_fill].replace(r"^\s*$", pd.NA, regex=True).ffill()
            )

    return dataframe.reset_index(drop=True)


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

        amount = _resolve_amount(row, normalised_columns)
        if amount is None:
            errors.append(
                {
                    "field": f"Row {row_number} - Amount",
                    "message": "Amount must be present as Amount + GST or derivable from Qty x Unit Rate.",
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
        pr_status = normalize_text(row[column_map["PR Status"]])
        po_number = _optional_text(row, column_map, "PO")
        po_status = _optional_text(row, column_map, "PO Status")
        requestor = normalize_text(row[column_map["Requestor"]])
        purpose = normalize_text(row[column_map["Purpose"]])
        item_details = normalize_text(row[column_map["Item Details"]])
        wbs = normalize_text(row[column_map["WBS"]])
        instruction = _optional_text(row, column_map, "Instruction to Vendor")

        req_type = _optional_text(row, column_map, "Req Type")
        pr_category = _optional_text(row, column_map, "PR Category")  # RESTORED

        lab = _optional_text(row, column_map, "Lab")
        pr_sub_date = _format_date(row[column_map["PR Sub Date"]])
        grand_total = parse_decimal(row[column_map["Grand Total in SGD"]])
        quantity = parse_decimal(row[column_map["Qty"]])
        unit_rate = parse_decimal(row[column_map["Unit Rate"]])
        amount_gst = _resolve_amount(row, column_map)

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
                "pr_status": pr_status,
                "po_number": po_number,
                "po_status": po_status,
                "pr_sub_date": pr_sub_date,
                "requestor": requestor,
                "purpose": purpose,
                "grand_total_sgd": _decimal_to_text(grand_total),
                "item_details": item_details,
                "quantity": _decimal_to_text(quantity),
                "unit_rate": _decimal_to_text(unit_rate),
                "wbs": wbs,
                "instruction_to_vendor": instruction,
                "req_type": req_type,
                "pr_category": pr_category,  # RESTORED
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
                pr_status=pr_status,
                po_number=po_number,
                po_status=po_status,
                grand_total_sgd=grand_total,
                item_details=item_details,
                quantity=quantity,
                unit_rate=unit_rate,
                wbs=wbs,
                instruction_to_vendor=instruction,
                req_type=req_type,
                pr_category=pr_category,  # RESTORED
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
