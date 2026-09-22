"""
Excel report generation for PR Records (W11-03 reporting).

Builds a styled .xlsx workbook from the same role-scoped, filter-applied
CommittedPR rows that the PR Records page displays, so the file always
matches what the user can actually see on screen.

Workbook layout:
  Sheet "PR Records" — branded cover block (who generated it, under which
    role scope, which filters were active) above a flat one-row-per-line
    Excel table, frozen and auto-filtered, with a bold total row.
  Sheet "Summary"    — totals broken down by lab group, lab, category and
    line status, each with a data-bar % column.

Only openpyxl is used (already a dependency via the upload parser), so this
adds no new packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Iterable, Sequence

from openpyxl import Workbook
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

# ─── Brand palette (mirrors the frontend's Tailwind tokens) ──────────────
NAVY = "1E3A8A"
NAVY_LIGHT = "1E40AF"
BLUE_TINT = "F0F9FF"
BORDER_GREY = "E5E7EB"
MUTED_TEXT = "6B7280"
WHITE = "FFFFFF"

MONEY_FMT = "#,##0.00"
QTY_FMT = "#,##0.####"
DATE_FMT = "dd mmm yyyy"
PERCENT_FMT = '0.0"%"'

_THIN = Side(style="thin", color=BORDER_GREY)
_BOX = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


@dataclass
class ReportMeta:
    """Everything the cover block needs to describe this export."""

    generated_at: datetime
    generated_by_name: str
    generated_by_email: str
    role_label: str
    scope_label: str
    fy_label: str
    date_range_label: str
    search_label: str
    lab_group_label: str


# Sheet 1 columns. (header, width, number format or None)
_COLUMNS: list[tuple[str, int, str | None]] = [
    ("PR Number", 16, None),
    ("PR Date", 14, DATE_FMT),
    ("Requestor", 22, None),
    ("Purpose", 30, None),
    ("WBS Code", 16, None),
    ("Lab Group", 20, None),
    ("Line", 7, "0"),
    ("Item Description", 42, None),
    ("Lab", 24, None),
    ("Category", 18, None),
    ("Qty", 9, QTY_FMT),
    ("Unit Rate", 14, MONEY_FMT),
    ("Currency", 10, None),
    ("Amount + GST", 16, MONEY_FMT),
    ("Line Status", 20, None),
]

_AMOUNT_COL = 14  # 1-indexed position of "Amount + GST"


def build_pr_records_workbook(prs: Sequence[Any], meta: ReportMeta) -> BytesIO:
    """Render the PR Records report and return it as an in-memory .xlsx."""
    wb = Workbook()
    records_ws = wb.active
    records_ws.title = "PR Records"

    rows = _flatten(prs)
    _build_records_sheet(records_ws, rows, meta, pr_count=len(prs))

    summary_ws = wb.create_sheet("Summary")
    _build_summary_sheet(summary_ws, rows, meta, pr_count=len(prs))

    stream = BytesIO()
    wb.save(stream)
    stream.seek(0)
    return stream


# ─── Row flattening ──────────────────────────────────────────────────────
def _flatten(prs: Sequence[Any]) -> list[dict[str, Any]]:
    """One dict per PR line, with the PR-level fields denormalised onto it.

    A PR with no visible lines still contributes a single row so the export
    never silently drops a record the page listed.
    """
    rows: list[dict[str, Any]] = []
    for pr in prs:
        base = {
            "pr_number": pr.source_pr_number,
            "pr_date": _as_date(pr.request_date),
            "requestor": pr.requestor_name or "",
            "purpose": pr.purpose or "",
            "wbs": pr.wbs_code or "",
            "lab_group": pr.lab_group_name or "General",
        }
        if not pr.lines:
            rows.append(
                {
                    **base,
                    "line_no": None,
                    "item": "(no visible lines)",
                    "lab": "",
                    "category": "",
                    "qty": None,
                    "unit_rate": None,
                    "currency": "",
                    "amount": _as_number(pr.grand_total_sgd) or 0.0,
                    "status": pr.pr_status or "",
                }
            )
            continue
        for line in pr.lines:
            rows.append(
                {
                    **base,
                    "line_no": line.line_no,
                    "item": line.item_description or "",
                    "lab": line.lab_name or "",
                    "category": line.category_name or "",
                    "qty": _as_number(line.qty),
                    "unit_rate": _as_number(line.unit_rate),
                    "currency": line.currency_code or "SGD",
                    "amount": _as_number(line.amount_gst) or 0.0,
                    "status": line.pr_status or pr.pr_status or "",
                }
            )
    return rows


def _as_number(raw: Any) -> float | None:
    if raw is None or raw == "":
        return None
    try:
        return float(Decimal(str(raw)))
    except (InvalidOperation, ValueError):
        return None


def _as_date(raw: str | None) -> date | None:
    if not raw:
        return None
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


# ─── Sheet 1: PR Records ─────────────────────────────────────────────────
def _build_records_sheet(
    ws: Worksheet, rows: list[dict[str, Any]], meta: ReportMeta, pr_count: int
) -> None:
    ncols = len(_COLUMNS)
    total_amount = sum(r["amount"] or 0.0 for r in rows)

    cursor = _write_cover(
        ws,
        meta,
        ncols,
        extra_rows=[
            (
                "Records",
                f"{pr_count} PR{'' if pr_count == 1 else 's'} · "
                f"{len(rows)} line{'' if len(rows) == 1 else 's'}",
            ),
            ("Total Value", f"SGD {total_amount:,.2f}"),
        ],
    )

    header_row = cursor + 1
    for idx, (title, _width, _fmt) in enumerate(_COLUMNS, start=1):
        cell = ws.cell(row=header_row, column=idx, value=title)
        cell.font = Font(bold=True, color=WHITE, size=10)
        cell.fill = PatternFill("solid", fgColor=NAVY)
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = _BOX
    ws.row_dimensions[header_row].height = 26

    keys = [
        "pr_number",
        "pr_date",
        "requestor",
        "purpose",
        "wbs",
        "lab_group",
        "line_no",
        "item",
        "lab",
        "category",
        "qty",
        "unit_rate",
        "currency",
        "amount",
        "status",
    ]
    for offset, row in enumerate(rows):
        excel_row = header_row + 1 + offset
        for idx, (key, (_title, _width, fmt)) in enumerate(
            zip(keys, _COLUMNS), start=1
        ):
            cell = ws.cell(row=excel_row, column=idx, value=row[key])
            cell.font = Font(size=10)
            cell.border = _BOX
            if fmt:
                cell.number_format = fmt
            if key in {"qty", "unit_rate", "amount", "line_no"}:
                cell.alignment = Alignment(horizontal="right")
            elif key in {"item", "purpose"}:
                cell.alignment = Alignment(vertical="top", wrap_text=True)

    last_data_row = header_row + len(rows)

    # A real Excel table gives banded rows + filter dropdowns for free.
    if rows:
        ref = f"A{header_row}:{get_column_letter(ncols)}{last_data_row}"
        table = Table(displayName="PRRecords", ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleLight9", showRowStripes=True, showColumnStripes=False
        )
        ws.add_table(table)
    else:
        note = ws.cell(
            row=header_row + 1,
            column=1,
            value="No PR records matched the selected filters.",
        )
        note.font = Font(italic=True, color=MUTED_TEXT, size=10)
        ws.merge_cells(
            start_row=header_row + 1,
            start_column=1,
            end_row=header_row + 1,
            end_column=ncols,
        )
        last_data_row = header_row + 1

    # Bold total row directly beneath the table.
    total_row = last_data_row + 1
    label = ws.cell(row=total_row, column=1, value="TOTAL")
    label.font = Font(bold=True, size=10, color=NAVY)
    ws.merge_cells(
        start_row=total_row,
        start_column=1,
        end_row=total_row,
        end_column=_AMOUNT_COL - 1,
    )
    label.alignment = Alignment(horizontal="right")
    total_cell = ws.cell(row=total_row, column=_AMOUNT_COL, value=total_amount)
    total_cell.font = Font(bold=True, size=10, color=NAVY)
    total_cell.number_format = MONEY_FMT
    total_cell.alignment = Alignment(horizontal="right")
    for col in range(1, ncols + 1):
        ws.cell(row=total_row, column=col).fill = PatternFill(
            "solid", fgColor=BLUE_TINT
        )
        ws.cell(row=total_row, column=col).border = _BOX

    for idx, (_title, width, _fmt) in enumerate(_COLUMNS, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width

    # Keep the cover + header visible while scrolling the data.
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.sheet_view.showGridLines = False
    _set_print_setup(ws, ncols, header_row)


# ─── Sheet 2: Summary ────────────────────────────────────────────────────
def _build_summary_sheet(
    ws: Worksheet, rows: list[dict[str, Any]], meta: ReportMeta, pr_count: int
) -> None:
    ncols = 5
    cursor = _write_cover(ws, meta, ncols, extra_rows=[], compact=True)
    total_amount = sum(r["amount"] or 0.0 for r in rows) or 0.0

    cursor += 1
    for title, key in (
        ("Spending by Lab Group", "lab_group"),
        ("Spending by Lab", "lab"),
        ("Spending by Category", "category"),
        ("Spending by Line Status", "status"),
    ):
        cursor = _write_breakdown(ws, cursor, title, rows, key, total_amount)
        cursor += 2

    widths = [34, 10, 10, 18, 14]
    for idx, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.sheet_view.showGridLines = False


def _write_breakdown(
    ws: Worksheet,
    start_row: int,
    title: str,
    rows: list[dict[str, Any]],
    key: str,
    total_amount: float,
) -> int:
    """Write one titled breakdown block; returns the last row it used."""
    heading = ws.cell(row=start_row, column=1, value=title)
    heading.font = Font(bold=True, size=11, color=NAVY)
    ws.merge_cells(start_row=start_row, start_column=1, end_row=start_row, end_column=5)

    header_row = start_row + 1
    for idx, label in enumerate(
        ("Name", "PRs", "Lines", "Amount + GST", "% of Total"), start=1
    ):
        cell = ws.cell(row=header_row, column=idx, value=label)
        cell.font = Font(bold=True, size=10, color=WHITE)
        cell.fill = PatternFill("solid", fgColor=NAVY_LIGHT)
        cell.alignment = Alignment(horizontal="center")
        cell.border = _BOX

    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        name = str(row[key] or "—")
        bucket = buckets.setdefault(name, {"amount": 0.0, "lines": 0, "prs": set()})
        bucket["amount"] += row["amount"] or 0.0
        bucket["lines"] += 1
        bucket["prs"].add(row["pr_number"])

    ordered = sorted(buckets.items(), key=lambda kv: kv[1]["amount"], reverse=True)

    cursor = header_row
    for name, bucket in ordered:
        cursor += 1
        pct = (bucket["amount"] / total_amount * 100) if total_amount else 0.0
        values: list[Any] = [
            name,
            len(bucket["prs"]),
            bucket["lines"],
            bucket["amount"],
            pct,
        ]
        for idx, value in enumerate(values, start=1):
            cell = ws.cell(row=cursor, column=idx, value=value)
            cell.font = Font(size=10)
            cell.border = _BOX
            if idx == 4:
                cell.number_format = MONEY_FMT
            elif idx == 5:
                cell.number_format = PERCENT_FMT
            if idx in (2, 3, 4, 5):
                cell.alignment = Alignment(horizontal="right")

    if not ordered:
        cursor += 1
        cell = ws.cell(row=cursor, column=1, value="No data for the selected filters.")
        cell.font = Font(italic=True, color=MUTED_TEXT, size=10)
        return cursor

    # Total row for the block.
    cursor += 1
    total_label = ws.cell(row=cursor, column=1, value="Total")
    total_label.font = Font(bold=True, size=10)
    total_label.fill = PatternFill("solid", fgColor=BLUE_TINT)
    total_label.border = _BOX
    # Count DISTINCT PRs, not the sum of per-bucket counts: one PR can have
    # lines in several categories/labs and would otherwise be counted twice.
    distinct_prs: set[str] = set()
    for _name, bucket in ordered:
        distinct_prs |= bucket["prs"]
    for idx, value in (
        (2, len(distinct_prs)),
        (3, sum(b["lines"] for _n, b in ordered)),
        (4, total_amount),
        (5, 100.0 if total_amount else 0.0),
    ):
        cell = ws.cell(row=cursor, column=idx, value=value)
        cell.font = Font(bold=True, size=10)
        cell.fill = PatternFill("solid", fgColor=BLUE_TINT)
        cell.border = _BOX
        cell.alignment = Alignment(horizontal="right")
        if idx == 4:
            cell.number_format = MONEY_FMT
        elif idx == 5:
            cell.number_format = PERCENT_FMT

    # Data bars make the distribution readable at a glance.
    data_start = header_row + 1
    data_end = cursor - 1
    if data_end >= data_start:
        ws.conditional_formatting.add(
            f"E{data_start}:E{data_end}",
            DataBarRule(
                start_type="num",
                start_value=0,
                end_type="num",
                end_value=100,
                color="3B82F6",
                showValue=True,
            ),
        )
    return cursor


# ─── Shared cover block ──────────────────────────────────────────────────
def _write_cover(
    ws: Worksheet,
    meta: ReportMeta,
    ncols: int,
    extra_rows: Iterable[tuple[str, str]],
    compact: bool = False,
) -> int:
    """Write the branded title + filter-context block. Returns the last row used."""
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    title = ws.cell(row=1, column=1, value="LAB BUDGET MONITORING SYSTEM")
    title.font = Font(bold=True, size=14, color=WHITE)
    title.fill = PatternFill("solid", fgColor=NAVY)
    title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    subtitle = ws.cell(row=2, column=1, value="Purchase Request Records Report")
    subtitle.font = Font(size=11, color=WHITE)
    subtitle.fill = PatternFill("solid", fgColor=NAVY_LIGHT)
    subtitle.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

    meta_rows: list[tuple[str, str]] = [
        ("Generated", meta.generated_at.strftime("%d %b %Y, %I:%M %p")),
        ("Generated by", f"{meta.generated_by_name} ({meta.generated_by_email})"),
        ("Role", meta.role_label),
        ("Scope", meta.scope_label),
        ("Fiscal Year", meta.fy_label),
        ("Date Range", meta.date_range_label),
        ("Lab Group Filter", meta.lab_group_label),
        ("Search", meta.search_label),
    ]
    if compact:
        meta_rows = meta_rows[:2] + meta_rows[3:6]
    meta_rows.extend(extra_rows)

    cursor = 3
    for label, value in meta_rows:
        cursor += 1
        label_cell = ws.cell(row=cursor, column=1, value=label)
        label_cell.font = Font(bold=True, size=9, color=MUTED_TEXT)
        label_cell.alignment = Alignment(horizontal="left", indent=1)
        value_cell = ws.cell(row=cursor, column=2, value=value)
        value_cell.font = Font(size=10)
        value_cell.alignment = Alignment(horizontal="left")
        span_end = min(ncols, 6)
        if span_end > 2:
            ws.merge_cells(
                start_row=cursor,
                start_column=2,
                end_row=cursor,
                end_column=span_end,
            )
    return cursor + 1


def _set_print_setup(ws: Worksheet, ncols: int, header_row: int) -> None:
    """Landscape, fit-to-width, with the table header repeating on every page."""
    ws.page_setup.orientation = "landscape"
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f"{header_row}:{header_row}"
    ws.print_area = f"A1:{get_column_letter(ncols)}{ws.max_row}"
