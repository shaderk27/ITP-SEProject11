"""
Shared look-and-feel for generated .xlsx reports.

Both the PR Records export and the Dashboard export produce workbooks that
should read as the same family of documents, so the palette, number formats
and the branded cover block live here rather than being copy-pasted.

Colours mirror the frontend's Tailwind tokens.
"""

from __future__ import annotations

from typing import Iterable, Sequence

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.worksheet.worksheet import Worksheet

# ─── Brand palette ───────────────────────────────────────────────────────
NAVY = "1E3A8A"
NAVY_LIGHT = "1E40AF"
BLUE = "3B82F6"
TEAL = "0D9488"
AMBER = "F59E0B"
RED = "DC2626"
BLUE_TINT = "F0F9FF"
GREY_TINT = "F8FAFC"
BORDER_GREY = "E5E7EB"
MUTED_TEXT = "6B7280"
WHITE = "FFFFFF"

# ─── Number formats ──────────────────────────────────────────────────────
MONEY_FMT = "#,##0.00"
QTY_FMT = "#,##0.####"
DATE_FMT = "dd mmm yyyy"
PERCENT_FMT = '0.0"%"'

THIN_SIDE = Side(style="thin", color=BORDER_GREY)
BOX_BORDER = Border(left=THIN_SIDE, right=THIN_SIDE, top=THIN_SIDE, bottom=THIN_SIDE)

REPORT_TITLE = "LAB BUDGET MONITORING SYSTEM"


def write_cover(
    ws: Worksheet,
    subtitle: str,
    meta_rows: Iterable[tuple[str, str]],
    ncols: int,
) -> int:
    """
    Write the branded title bar plus a label/value context block.

    ``meta_rows`` records who generated the report, under which role scope and
    with which filters — the things that make a downloaded file auditable
    months later. Returns the last row used.
    """
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=ncols)
    title = ws.cell(row=1, column=1, value=REPORT_TITLE)
    title.font = Font(bold=True, size=14, color=WHITE)
    title.fill = PatternFill("solid", fgColor=NAVY)
    title.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[1].height = 30

    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=ncols)
    sub = ws.cell(row=2, column=1, value=subtitle)
    sub.font = Font(size=11, color=WHITE)
    sub.fill = PatternFill("solid", fgColor=NAVY_LIGHT)
    sub.alignment = Alignment(horizontal="left", vertical="center", indent=1)
    ws.row_dimensions[2].height = 20

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


def write_table_header(
    ws: Worksheet, row: int, headers: Sequence[str], fill: str = NAVY
) -> None:
    """Bold, filled, wrapped header row with borders."""
    for idx, label in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=idx, value=label)
        cell.font = Font(bold=True, color=WHITE, size=10)
        cell.fill = PatternFill("solid", fgColor=fill)
        cell.alignment = Alignment(
            horizontal="center", vertical="center", wrap_text=True
        )
        cell.border = BOX_BORDER
    ws.row_dimensions[row].height = 26
