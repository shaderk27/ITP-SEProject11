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

The remaining sheets carry what the uploader's own Excel can't tell them —
what the system worked out after the upload (see records_insights_service):
  Sheet "Action Items"         — long-pending lines, possible duplicate
    purchases, lines parked in a General lab, PRs that tipped a lab budget,
    rejected lines.
  Sheet "Budget Impact"        — each PR placed on its lab's FY budget
    timeline: used before / after, % used, balance, alert crossed.
  Sheet "Change History"       — field-level changes between uploads.
  Sheet "Classification Trail" — how each line got its lab / category, who
    reviewed it, and which upload it came from.

Only openpyxl is used (already a dependency via the upload parser), so this
adds no new packages.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from io import BytesIO
from typing import Any, Callable, Iterable, Sequence

from openpyxl import Workbook
from openpyxl.formatting.rule import DataBarRule
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.worksheet.worksheet import Worksheet

from app.services.records_insights_service import ExportInsights

# ─── Brand palette (mirrors the frontend's Tailwind tokens) ──────────────
NAVY = "1E3A8A"
NAVY_LIGHT = "1E40AF"
BLUE_TINT = "F0F9FF"
BORDER_GREY = "E5E7EB"
MUTED_TEXT = "6B7280"
WHITE = "FFFFFF"
AMBER_TINT = "FEF3C7"
RED_TINT = "FEE2E2"
GREEN_TEXT = "15803D"

# A line still Pending after this many days is called out on Action Items.
STALE_PENDING_DAYS = 30

MONEY_FMT = "#,##0.00"
QTY_FMT = "#,##0.####"
DATE_FMT = "dd mmm yyyy"
DATETIME_FMT = "dd mmm yyyy hh:mm"
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


def build_pr_records_workbook(
    prs: Sequence[Any], meta: ReportMeta, insights: ExportInsights | None = None
) -> BytesIO:
    """Render the PR Records report and return it as an in-memory .xlsx."""
    insights = insights or ExportInsights()
    wb = Workbook()
    records_ws = wb.active
    records_ws.title = "PR Records"

    rows = _flatten(prs)
    _build_records_sheet(records_ws, rows, meta, pr_count=len(prs))

    summary_ws = wb.create_sheet("Summary")
    _build_summary_sheet(summary_ws, rows, meta, pr_count=len(prs))

    _build_action_items_sheet(wb.create_sheet("Action Items"), rows, meta, insights)
    _build_budget_impact_sheet(wb.create_sheet("Budget Impact"), meta, insights)
    _build_change_history_sheet(wb.create_sheet("Change History"), meta, insights)
    _build_trail_sheet(wb.create_sheet("Classification Trail"), rows, meta, insights)

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
                    "pr_line_id": None,
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
                    "pr_line_id": line.pr_line_id,
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


# ─── Sheet 3: Action Items ───────────────────────────────────────────────
_ACTION_WIDTHS = [16, 14, 14, 20, 26, 44, 16, 26]

_PENDING_COLS: list[tuple[str, int, str | None]] = [
    ("PR Number", 0, None),
    ("PR Date", 0, DATE_FMT),
    ("Days Waiting", 0, "0"),
    ("Requestor", 0, None),
    ("Lab", 0, None),
    ("Item Description", 0, None),
    ("Amount + GST", 0, MONEY_FMT),
    ("Line Status", 0, None),
]
_DUPLICATE_COLS: list[tuple[str, int, str | None]] = [
    ("Match", 0, None),
    ("PR Number", 0, None),
    ("PR Date", 0, DATE_FMT),
    ("Requestor", 0, None),
    ("Lab", 0, None),
    ("Item Description", 0, None),
    ("Amount + GST", 0, MONEY_FMT),
    ("Line Status", 0, None),
]
_GENERAL_COLS: list[tuple[str, int, str | None]] = [
    ("PR Number", 0, None),
    ("PR Date", 0, DATE_FMT),
    ("Requestor", 0, None),
    ("Lab Group", 0, None),
    ("Lab", 0, None),
    ("Item Description", 0, None),
    ("Amount + GST", 0, MONEY_FMT),
    ("Category", 0, None),
]
_ALERT_COLS: list[tuple[str, int, str | None]] = [
    ("PR Number", 0, None),
    ("PR Date", 0, DATE_FMT),
    ("Lab Group", 0, None),
    ("Lab", 0, None),
    ("% Used After", 0, PERCENT_FMT),
    ("Alert", 0, None),
    ("Counted Amount", 0, MONEY_FMT),
    ("Balance After", 0, MONEY_FMT),
]
_REJECTED_COLS: list[tuple[str, int, str | None]] = [
    ("PR Number", 0, None),
    ("PR Date", 0, DATE_FMT),
    ("Requestor", 0, None),
    ("Lab", 0, None),
    ("Category", 0, None),
    ("Item Description", 0, None),
    ("Amount + GST", 0, MONEY_FMT),
    ("Line Status", 0, None),
]


def _build_action_items_sheet(
    ws: Worksheet,
    rows: list[dict[str, Any]],
    meta: ReportMeta,
    insights: ExportInsights,
) -> None:
    ncols = len(_ACTION_WIDTHS)
    today = meta.generated_at.date()
    real_rows = [r for r in rows if r["pr_line_id"] is not None]

    # Pending lines, oldest first.
    pending = []
    for r in real_rows:
        if not r["status"].strip().lower().startswith("pending"):
            continue
        days = (today - r["pr_date"]).days if r["pr_date"] else None
        pending.append((r, days))
    pending.sort(key=lambda p: -1 if p[1] is None else p[1], reverse=True)
    stale_count = sum(
        1 for _r, d in pending if d is not None and d > STALE_PENDING_DAYS
    )

    # Same item + same amount on different PRs.
    by_key: dict[tuple[str, float], list[dict[str, Any]]] = {}
    for r in real_rows:
        item = " ".join(r["item"].lower().split())
        if item:
            by_key.setdefault((item, round(r["amount"] or 0.0, 2)), []).append(r)
    duplicates = [
        group for group in by_key.values() if len({r["pr_number"] for r in group}) > 1
    ]
    duplicates.sort(key=lambda g: -(g[0]["amount"] or 0.0))

    general = [r for r in real_rows if "general" in r["lab"].lower()]

    alerts = [
        e
        for e in insights.impact
        if e.flag.startswith(("Crossed", "Pushed", "Used up"))
    ]

    rejected = [
        r for r in real_rows if r["status"].strip().lower().startswith("rejected")
    ]
    rejected_total = sum(r["amount"] or 0.0 for r in rejected)

    cursor = _write_cover(ws, meta, ncols, extra_rows=[], compact=True)
    cursor = _write_heading(
        ws,
        cursor + 1,
        "At a glance",
        "Things in this export that may need follow-up. Each item is listed in "
        "its own section below.",
        ncols,
    )
    for label, value in (
        (f"Pending lines older than {STALE_PENDING_DAYS} days", stale_count),
        ("Possible duplicate purchases", len(duplicates)),
        ("Lines sitting in a General lab", len(general)),
        ("PRs that set off a budget alert", len(alerts)),
        ("Rejected value (SGD)", rejected_total),
    ):
        cursor += 1
        label_cell = ws.cell(row=cursor, column=1, value=label)
        label_cell.font = Font(size=10)
        ws.merge_cells(start_row=cursor, start_column=1, end_row=cursor, end_column=3)
        value_cell = ws.cell(row=cursor, column=4, value=value)
        value_cell.font = Font(bold=True, size=10, color=NAVY)
        value_cell.alignment = Alignment(horizontal="right")
        if isinstance(value, float):
            value_cell.number_format = MONEY_FMT

    cursor = _write_section(
        ws,
        cursor + 2,
        "Pending lines, oldest first",
        f"Lines still Pending, counted in days from the PR date to the day this "
        f"report was generated. Over {STALE_PENDING_DAYS} days is highlighted.",
        _PENDING_COLS,
        [
            [
                r["pr_number"],
                r["pr_date"],
                days,
                r["requestor"],
                r["lab"],
                r["item"],
                r["amount"],
                r["status"],
            ]
            for r, days in pending
        ],
        highlight=lambda v: (
            AMBER_TINT if v[2] is not None and v[2] > STALE_PENDING_DAYS else None
        ),
    )

    duplicate_rows: list[list[Any]] = []
    for idx, group in enumerate(duplicates, start=1):
        for r in group:
            duplicate_rows.append(
                [
                    f"#{idx}",
                    r["pr_number"],
                    r["pr_date"],
                    r["requestor"],
                    r["lab"],
                    r["item"],
                    r["amount"],
                    r["status"],
                ]
            )
    cursor = _write_section(
        ws,
        cursor + 2,
        "Possible duplicate purchases",
        "Lines on different PRs with the same item description and amount. "
        "Check they are not the same purchase raised twice.",
        _DUPLICATE_COLS,
        duplicate_rows,
    )

    cursor = _write_section(
        ws,
        cursor + 2,
        "Lines sitting in a General lab",
        "The system could not tell which lab these belong to, so they were "
        "placed in the lab group's General lab. Consider assigning a real lab.",
        _GENERAL_COLS,
        [
            [
                r["pr_number"],
                r["pr_date"],
                r["requestor"],
                r["lab_group"],
                r["lab"],
                r["item"],
                r["amount"],
                r["category"],
            ]
            for r in general
        ],
    )

    cursor = _write_section(
        ws,
        cursor + 2,
        "PRs that set off a budget alert",
        "The PR that took its lab past a 50 / 80 / 95 / 100% alert level. "
        "See the Budget Impact sheet for every PR.",
        _ALERT_COLS,
        [
            [
                e.pr_number,
                e.pr_date,
                e.lab_group,
                e.lab,
                e.pct_after,
                e.flag,
                e.counted_amount,
                e.balance_after,
            ]
            for e in alerts
        ],
        highlight=lambda v: _flag_tint(v[5]),
    )

    _write_section(
        ws,
        cursor + 2,
        f"Rejected lines (SGD {rejected_total:,.2f})",
        "Rejected lines are not counted toward any budget.",
        _REJECTED_COLS,
        [
            [
                r["pr_number"],
                r["pr_date"],
                r["requestor"],
                r["lab"],
                r["category"],
                r["item"],
                r["amount"],
                r["status"],
            ]
            for r in rejected
        ],
    )

    for idx, width in enumerate(_ACTION_WIDTHS, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.sheet_view.showGridLines = False
    _set_print_setup(ws, ncols, header_row=1)


# ─── Sheet 4: Budget Impact ──────────────────────────────────────────────
_IMPACT_COLS: list[tuple[str, int, str | None]] = [
    ("PR Date", 13, DATE_FMT),
    ("PR Number", 16, None),
    ("Requestor", 18, None),
    ("Lab Group", 14, None),
    ("Lab", 24, None),
    ("FY", 9, None),
    ("Line Status", 18, None),
    ("PR Amount", 13, MONEY_FMT),
    ("Counted Amount", 13, MONEY_FMT),
    ("Lab FY Budget", 13, MONEY_FMT),
    ("Used Before", 13, MONEY_FMT),
    ("Used After", 13, MONEY_FMT),
    ("% Used After", 11, PERCENT_FMT),
    ("Balance After", 13, MONEY_FMT),
    ("Alert", 30, None),
]


def _build_budget_impact_sheet(
    ws: Worksheet, meta: ReportMeta, insights: ExportInsights
) -> None:
    _build_table_sheet(
        ws,
        meta,
        title="Where each PR left its lab's budget",
        note=(
            "Counted Amount = Approved + Pending lines (same rule as the "
            "dashboard). Used Before / After is the lab's running total from "
            "the start of its financial year in PR-date order, including PRs "
            "outside this export's filters. One row per PR per lab."
        ),
        columns=_IMPACT_COLS,
        values_rows=[
            [
                e.pr_date,
                e.pr_number,
                e.requestor,
                e.lab_group,
                e.lab,
                e.fy_label,
                e.status,
                e.amount,
                e.counted_amount,
                e.budget,
                e.used_before,
                e.used_after,
                e.pct_after,
                e.balance_after,
                e.flag,
            ]
            for e in insights.impact
        ],
        table_name="BudgetImpact",
        empty_message="No PR lines in this export are linked to a lab.",
        highlight=lambda v: _flag_tint(v[14]),
    )


# ─── Sheet 5: Change History ─────────────────────────────────────────────
_CHANGE_COLS: list[tuple[str, int, str | None]] = [
    ("Changed On", 18, DATETIME_FMT),
    ("PR Number", 16, None),
    ("What Changed", 18, None),
    ("Old Value", 22, None),
    ("New Value", 22, None),
    ("Upload File", 34, None),
    ("Uploaded By", 22, None),
]


def _build_change_history_sheet(
    ws: Worksheet, meta: ReportMeta, insights: ExportInsights
) -> None:
    _build_table_sheet(
        ws,
        meta,
        title="What changed between uploads",
        note=(
            "When a PR is uploaded again, the system compares it with what it "
            "already had. Each row is one field that changed. A reviewer's "
            "lab / category choice is kept across re-uploads."
        ),
        columns=_CHANGE_COLS,
        values_rows=[
            [
                c.changed_at,
                c.pr_number,
                c.field,
                c.old_value,
                c.new_value,
                c.source_file,
                c.changed_by,
            ]
            for c in insights.changes
        ],
        table_name="ChangeHistory",
        empty_message="No PR in this export has changed between uploads.",
    )


# ─── Sheet 6: Classification Trail ───────────────────────────────────────
_TRAIL_COLS: list[tuple[str, int, str | None]] = [
    ("PR Number", 16, None),
    ("Line", 7, "0"),
    ("Item Description", 36, None),
    ("Uploaded Lab Text", 20, None),
    ("Uploaded Category", 16, None),
    ("Assigned Lab", 22, None),
    ("Assigned Category", 16, None),
    ("How Assigned", 20, None),
    ("Reason", 36, None),
    ("Reviewed By", 18, None),
    ("Reviewed On", 17, DATETIME_FMT),
    ("Review Comment", 26, None),
    ("Times Uploaded", 10, "0"),
    ("Latest Upload File", 30, None),
    ("Uploaded By", 18, None),
    ("Uploaded On", 17, DATETIME_FMT),
]


def _build_trail_sheet(
    ws: Worksheet,
    rows: list[dict[str, Any]],
    meta: ReportMeta,
    insights: ExportInsights,
) -> None:
    values_rows: list[list[Any]] = []
    for r in rows:
        if r["pr_line_id"] is None:
            continue
        t = insights.trail.get(r["pr_line_id"])
        values_rows.append(
            [
                r["pr_number"],
                r["line_no"],
                r["item"],
                t.uploaded_lab_text if t else "",
                t.uploaded_category if t else "",
                r["lab"],
                r["category"],
                t.method if t else "No upload record",
                t.reason if t else "",
                t.reviewed_by if t else "",
                t.reviewed_at if t else None,
                t.review_comment if t else "",
                t.upload_count if t else None,
                t.source_file if t else "",
                t.uploaded_by if t else "",
                t.uploaded_at if t else None,
            ]
        )
    _build_table_sheet(
        ws,
        meta,
        title="How each line got its lab and category",
        note=(
            "Uploaded Lab Text / Category are what the source file said; "
            "Assigned Lab / Category are what the system recorded. Lines the "
            "classifier could not place went to the Review Queue and show "
            "who reviewed them."
        ),
        columns=_TRAIL_COLS,
        values_rows=values_rows,
        table_name="ClassificationTrail",
        empty_message="No PR lines in this export.",
        highlight=lambda v: BLUE_TINT if v[7] == "Manually reviewed" else None,
    )


# ─── Shared table helpers ────────────────────────────────────────────────
def _build_table_sheet(
    ws: Worksheet,
    meta: ReportMeta,
    *,
    title: str,
    note: str,
    columns: list[tuple[str, int, str | None]],
    values_rows: list[list[Any]],
    table_name: str,
    empty_message: str,
    highlight: Callable[[list[Any]], str | None] | None = None,
) -> None:
    """Cover block + heading + one filterable Excel table."""
    ncols = len(columns)
    cursor = _write_cover(ws, meta, ncols, extra_rows=[], compact=True)
    cursor = _write_heading(ws, cursor + 1, title, note, ncols)

    header_row = cursor + 2
    _write_header_row(ws, header_row, columns, NAVY)
    for offset, values in enumerate(values_rows, start=1):
        _write_value_row(ws, header_row + offset, columns, values, highlight)

    if values_rows:
        ref = f"A{header_row}:{get_column_letter(ncols)}{header_row + len(values_rows)}"
        table = Table(displayName=table_name, ref=ref)
        table.tableStyleInfo = TableStyleInfo(
            name="TableStyleLight9", showRowStripes=False, showColumnStripes=False
        )
        ws.add_table(table)
    else:
        note_cell = ws.cell(row=header_row + 1, column=1, value=empty_message)
        note_cell.font = Font(italic=True, color=MUTED_TEXT, size=10)
        ws.merge_cells(
            start_row=header_row + 1,
            start_column=1,
            end_row=header_row + 1,
            end_column=ncols,
        )

    for idx, (_title, width, _fmt) in enumerate(columns, start=1):
        ws.column_dimensions[get_column_letter(idx)].width = width
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.sheet_view.showGridLines = False
    _set_print_setup(ws, ncols, header_row)


def _write_section(
    ws: Worksheet,
    start_row: int,
    title: str,
    note: str,
    columns: list[tuple[str, int, str | None]],
    values_rows: list[list[Any]],
    highlight: Callable[[list[Any]], str | None] | None = None,
) -> int:
    """One titled mini-table on the Action Items sheet. Returns the last row used."""
    ncols = len(columns)
    cursor = _write_heading(ws, start_row, title, note, ncols)
    if not values_rows:
        cursor += 1
        cell = ws.cell(row=cursor, column=1, value="None found.")
        cell.font = Font(italic=True, size=10, color=GREEN_TEXT)
        return cursor
    cursor += 1
    _write_header_row(ws, cursor, columns, NAVY_LIGHT)
    for values in values_rows:
        cursor += 1
        _write_value_row(ws, cursor, columns, values, highlight)
    return cursor


def _write_heading(ws: Worksheet, row: int, title: str, note: str, ncols: int) -> int:
    """Bold section title with a muted explanatory line under it."""
    heading = ws.cell(row=row, column=1, value=title)
    heading.font = Font(bold=True, size=11, color=NAVY)
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=ncols)
    if not note:
        return row
    note_cell = ws.cell(row=row + 1, column=1, value=note)
    note_cell.font = Font(italic=True, size=9, color=MUTED_TEXT)
    note_cell.alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells(start_row=row + 1, start_column=1, end_row=row + 1, end_column=ncols)
    ws.row_dimensions[row + 1].height = 30
    return row + 1


def _write_header_row(
    ws: Worksheet, row: int, columns: list[tuple[str, int, str | None]], fill: str
) -> None:
    for idx, (title, _width, _fmt) in enumerate(columns, start=1):
        cell = ws.cell(row=row, column=idx, value=title)
        cell.font = Font(bold=True, color=WHITE, size=10)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = _BOX
    ws.row_dimensions[row].height = 26


def _write_value_row(
    ws: Worksheet,
    row: int,
    columns: list[tuple[str, int, str | None]],
    values: list[Any],
    highlight: Callable[[list[Any]], str | None] | None,
) -> None:
    tint = highlight(values) if highlight else None
    for idx, (value, (_title, width, fmt)) in enumerate(zip(values, columns), start=1):
        cell = ws.cell(row=row, column=idx, value=value)
        cell.font = Font(size=10)
        cell.border = _BOX
        if fmt:
            cell.number_format = fmt
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            cell.alignment = Alignment(horizontal="right", vertical="top")
        else:
            cell.alignment = Alignment(vertical="top", wrap_text=True)
        if tint:
            cell.fill = PatternFill("solid", fgColor=tint)


def _flag_tint(flag: str | None) -> str | None:
    text = (flag or "").lower()
    if "over budget" in text or "used up" in text:
        return RED_TINT
    if text.startswith("crossed"):
        return AMBER_TINT
    return None


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
