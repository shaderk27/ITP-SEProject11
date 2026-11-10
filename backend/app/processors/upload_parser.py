from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from io import BytesIO
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

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
    "Curr",
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

_CENT = Decimal("0.01")


@dataclass(frozen=True)
class _ResolvedMoney:
    amount_sgd: Decimal
    unit_rate_sgd: Decimal | None
    source_currency: str
    source_unit_rate: Decimal | None
    source_amount: Decimal
    conversion_rate: Decimal


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
        dataframe = _read_csv(content)
    elif extension == "xls":
        dataframe = _read_legacy_xls(content)
    if extension == "xlsx":
        dataframe = _read_xlsx(content)
    elif extension not in {"csv", "xls"}:
        raise ValueError("Invalid file format. Upload a .csv, .xls, or .xlsx file.")

    return _prepare_source_rows(dataframe)


def _read_csv(content: bytes) -> pd.DataFrame:
    try:
        return pd.read_csv(BytesIO(content), dtype=object, encoding="utf-8-sig")
    except UnicodeDecodeError:
        return pd.read_csv(BytesIO(content), dtype=object, encoding="cp1252")


def _read_xlsx(content: bytes) -> pd.DataFrame:
    workbook = _normalise_strict_xlsx(content)
    dataframe = pd.read_excel(workbook, dtype=object)

    # Some source exports store leading-hyphen text as an Excel formula, for
    # example ``=-Small Order Delivery Charges``. With no cached formula value,
    # openpyxl returns a blank cell. Recover only that narrow text pattern so
    # genuine spreadsheet formulas continue to use their cached values.
    workbook.seek(0)
    formulas = pd.read_excel(
        workbook,
        dtype=object,
        engine_kwargs={"data_only": False},
    )
    shared_columns = dataframe.columns.intersection(formulas.columns)
    for column in shared_columns:
        blank_values = dataframe[column].map(lambda value: not normalize_text(value))
        formula_text = formulas[column].map(normalize_text)
        recoverable = blank_values & formula_text.str.match(r"^=-[A-Za-z]")
        if recoverable.any():
            dataframe.loc[recoverable, column] = formula_text.loc[recoverable].str[1:]

    return dataframe


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
        blank = dataframe[columns_to_fill].apply(
            lambda column: column.map(lambda value: not normalize_text(value))
        )
        is_continuation = blank.all(axis=1)
        parent = dataframe.index.to_series().where(~is_continuation).ffill()
        has_parent = is_continuation & parent.notna()
        for column in columns_to_fill:
            dataframe[column] = dataframe[column].astype(object)
            dataframe.loc[has_parent, column] = dataframe.loc[
                parent[has_parent].astype(int), column
            ].to_numpy()

    return _drop_repeated_allocation_copies(dataframe, normalised_columns)


def _drop_repeated_allocation_copies(
    dataframe: pd.DataFrame,
    column_map: dict[str, str],
) -> pd.DataFrame:
    """Count an allocation-split item once until exact WBS allocation is supported."""
    allocation_column = column_map.get("Allocatn")
    if allocation_column is None or "PR" not in column_map:
        return dataframe

    comparison_columns = [
        column_map[column]
        for column in (
            "Item Details",
            "Qty",
            "UOM",
            "Unit Rate",
            "Delivery Date",
            "Amount + GST",
        )
        if column in column_map
    ]
    seen_allocated_items: set[tuple[str, ...]] = set()
    keep_rows: list[bool] = []

    for _, row in dataframe.iterrows():
        allocation = normalize_text(row[allocation_column])
        if not allocation:
            keep_rows.append(True)
            continue

        item_key = (
            _identifier_text(row[column_map["PR"]]),
            *(normalize_key_part(row[column]) for column in comparison_columns),
        )
        is_repeated_allocation = item_key in seen_allocated_items
        keep_rows.append(not is_repeated_allocation)
        seen_allocated_items.add(item_key)

    return dataframe.loc[keep_rows].copy()


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

    try:
        _resolve_money_by_row(df, normalised_columns)
    except ValueError as error:
        errors.append(
            {
                "field": "Currency conversion",
                "message": str(error),
                "severity": "error",
            }
        )

    return errors


def parse_line_items(df: pd.DataFrame) -> list[PRLineItem]:
    column_map = {normalize_text(column): column for column in df.columns}
    items: list[PRLineItem] = []
    money_by_row = _resolve_money_by_row(df, column_map)
    identity_occurrences: dict[str, int] = {}

    for index, row in df.iterrows():
        row_number = int(index) + 2
        pr_number = _identifier_text(row[column_map["PR"]])
        pr_status = normalize_text(row[column_map["PR Status"]])
        po_number = _optional_identifier_text(row, column_map, "PO")
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
        money = money_by_row.get(int(index))

        if money is None:
            continue
        unit_rate = money.unit_rate_sgd
        amount_gst = money.amount_sgd

        base_identity_key = generate_line_identity_key(
            pr_number=pr_number,
            item_details=item_details,
            wbs=wbs,
            requestor=requestor,
            purpose=purpose,
        )
        occurrence = identity_occurrences.get(base_identity_key, 0) + 1
        identity_occurrences[base_identity_key] = occurrence
        identity_key = (
            base_identity_key
            if occurrence == 1
            else f"{base_identity_key}::occurrence_{occurrence}"
        )
        hash_fields = {
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
            "amount_gst": _decimal_to_text(
                _resolve_amount(row, column_map)
                if money.source_currency == "SGD"
                else amount_gst
            ),
        }
        if money.source_currency != "SGD":
            hash_fields.update(
                {
                    "source_currency": money.source_currency,
                    "source_unit_rate": _decimal_to_text(money.source_unit_rate),
                    "source_amount": _decimal_to_text(money.source_amount),
                }
            )
        content_hash = generate_content_hash(hash_fields)

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
                source_currency=money.source_currency,
                source_unit_rate=money.source_unit_rate,
                source_amount=money.source_amount,
                conversion_rate=money.conversion_rate,
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


def _optional_identifier_text(
    row: pd.Series,
    column_map: dict[str, str],
    column_name: str,
) -> str:
    source_column = column_map.get(column_name)
    if source_column is None:
        return ""
    return _identifier_text(row[source_column])


def _identifier_text(value: object) -> str:
    text = normalize_text(value)
    if not text:
        return ""
    if re.fullmatch(r"\d+\.0+", text):
        return text.split(".", 1)[0]
    return text


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


def _resolve_money_by_row(
    dataframe: pd.DataFrame,
    column_map: dict[str, str],
) -> dict[int, _ResolvedMoney]:
    amount_column = column_map.get("Amount + GST")
    currency_column = column_map.get("Curr")
    rows_by_pr: dict[str, list[dict[str, object]]] = {}

    for index, row in dataframe.iterrows():
        pr_number = _identifier_text(row[column_map["PR"]])
        source_currency = (
            normalize_text(row[currency_column]).upper() if currency_column else "SGD"
        ) or "SGD"
        quantity = parse_decimal(row[column_map["Qty"]])
        source_unit_rate = parse_decimal(row[column_map["Unit Rate"]])
        source_amount = (
            quantity * source_unit_rate
            if quantity is not None and source_unit_rate is not None
            else None
        )
        explicit_sgd = (
            parse_decimal(row[amount_column]) if amount_column is not None else None
        )
        grand_total_sgd = parse_decimal(row[column_map["Grand Total in SGD"]])

        if explicit_sgd is None and source_amount is None:
            continue

        rows_by_pr.setdefault(pr_number, []).append(
            {
                "index": int(index),
                "currency": source_currency,
                "source_unit_rate": source_unit_rate,
                "source_amount": source_amount,
                "explicit_sgd": explicit_sgd,
                "grand_total_sgd": grand_total_sgd,
            }
        )

    resolved: dict[int, _ResolvedMoney] = {}
    resolution_errors: list[str] = []
    for pr_number, entries in rows_by_pr.items():
        source_rows = ", ".join(str(int(entry["index"]) + 2) for entry in entries)
        pr_context = f"PR {pr_number} (source row(s) {source_rows})"
        currencies = {str(entry["currency"]) for entry in entries}
        if len(currencies) != 1:
            resolution_errors.append(
                f"{pr_context} contains mixed source currencies: "
                f"{', '.join(sorted(currencies))}."
            )
            continue
        currency = next(iter(currencies))

        if currency == "SGD":
            for entry in entries:
                source_amount = _entry_source_amount(entry)
                amount_sgd = _entry_base_amount(entry).quantize(
                    _CENT, rounding=ROUND_HALF_UP
                )
                source_unit_rate = _entry_decimal(entry, "source_unit_rate")
                resolved[int(entry["index"])] = _ResolvedMoney(
                    amount_sgd=amount_sgd,
                    unit_rate_sgd=source_unit_rate,
                    source_currency=currency,
                    source_unit_rate=source_unit_rate,
                    source_amount=source_amount,
                    conversion_rate=Decimal(1),
                )
            continue

        grand_total_sgd = _first_decimal(entries, "grand_total_sgd")
        if grand_total_sgd is None:
            resolution_errors.append(
                f"{pr_context} uses {currency} but has no Grand Total in SGD."
            )
            continue

        explicit_total = sum(
            (
                _entry_decimal(entry, "explicit_sgd") or Decimal(0)
                for entry in entries
            ),
            Decimal(0),
        )
        convertible = [
            entry for entry in entries if _entry_decimal(entry, "explicit_sgd") is None
        ]
        convertible_source_total = sum(
            (_entry_source_amount(entry) for entry in convertible), Decimal(0)
        )
        source_total = sum(
            (_entry_source_amount(entry) for entry in entries), Decimal(0)
        )
        target_convertible_sgd = grand_total_sgd - explicit_total

        if target_convertible_sgd < 0:
            resolution_errors.append(
                f"{pr_context} has explicit SGD line amounts above its SGD total."
            )
            continue
        if (
            convertible
            and convertible_source_total == 0
            and target_convertible_sgd != 0
        ):
            resolution_errors.append(
                f"{pr_context} cannot derive an SGD conversion from zero-valued "
                f"{currency} lines."
            )
            continue
        if not convertible and explicit_total != grand_total_sgd:
            resolution_errors.append(
                f"{pr_context} line amounts do not reconcile with Grand Total in SGD."
            )
            continue

        if convertible_source_total != 0:
            conversion_rate = target_convertible_sgd / convertible_source_total
        elif source_total != 0:
            conversion_rate = grand_total_sgd / source_total
        else:
            conversion_rate = Decimal(1)

        converted_indexes: list[int] = []
        for entry in entries:
            source_amount = _entry_source_amount(entry)
            explicit_sgd = _entry_decimal(entry, "explicit_sgd")
            amount_sgd = (
                explicit_sgd
                if explicit_sgd is not None
                else source_amount * conversion_rate
            ).quantize(_CENT, rounding=ROUND_HALF_UP)
            source_unit_rate = _entry_decimal(entry, "source_unit_rate")
            unit_rate_sgd = (
                (source_unit_rate * conversion_rate).quantize(
                    _CENT, rounding=ROUND_HALF_UP
                )
                if source_unit_rate is not None
                else None
            )
            index = int(entry["index"])
            resolved[index] = _ResolvedMoney(
                amount_sgd=amount_sgd,
                unit_rate_sgd=unit_rate_sgd,
                source_currency=currency,
                source_unit_rate=source_unit_rate,
                source_amount=source_amount,
                conversion_rate=conversion_rate,
            )
            if explicit_sgd is None:
                converted_indexes.append(index)

        rounded_total = sum(
            (resolved[int(entry["index"])].amount_sgd for entry in entries),
            Decimal(0),
        )
        rounding_difference = grand_total_sgd - rounded_total
        if rounding_difference and converted_indexes:
            final_index = converted_indexes[-1]
            final = resolved[final_index]
            resolved[final_index] = _ResolvedMoney(
                amount_sgd=final.amount_sgd + rounding_difference,
                unit_rate_sgd=final.unit_rate_sgd,
                source_currency=final.source_currency,
                source_unit_rate=final.source_unit_rate,
                source_amount=final.source_amount,
                conversion_rate=final.conversion_rate,
            )

    if resolution_errors:
        raise ValueError(" ".join(resolution_errors))

    return resolved


def _entry_decimal(entry: dict[str, object], key: str) -> Decimal | None:
    value = entry.get(key)
    return value if isinstance(value, Decimal) else None


def _entry_source_amount(entry: dict[str, object]) -> Decimal:
    value = _entry_decimal(entry, "source_amount")
    return value if value is not None else Decimal(0)


def _entry_base_amount(entry: dict[str, object]) -> Decimal:
    explicit_sgd = _entry_decimal(entry, "explicit_sgd")
    return explicit_sgd if explicit_sgd is not None else _entry_source_amount(entry)


def _first_decimal(entries: list[dict[str, object]], key: str) -> Decimal | None:
    return next(
        (
            value
            for entry in entries
            if (value := _entry_decimal(entry, key)) is not None
        ),
        None,
    )
