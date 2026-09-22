"""
W11-03 — PR Records Excel export.

Covers the three things the export has to get right:
  1. Role scoping — the workbook can only ever contain rows the caller is
     allowed to see (Admin all / Team Lead own group / Lab IC own lab).
  2. Filter fidelity — the page's client-side search and Lab Group filters
     are reproduced server-side so the file matches the screen.
  3. Workbook shape — cover block, flat line table, totals and summary
     breakdowns are present and arithmetically correct.
"""

from __future__ import annotations

from datetime import date, datetime
from io import BytesIO

import pytest
from openpyxl import load_workbook

from app.api.records import (
    CommittedPR,
    CommittedPRLine,
    _apply_view_filters,
    _date_range_label,
    _lab_group_label,
)
from app.services.report_service import ReportMeta, build_pr_records_workbook

HEADER_ROW_LABEL = "PR Number"


# ─── Builders ────────────────────────────────────────────────────────────
def _line(
    line_id: int,
    item: str = "Widget",
    lab: str = "W3L1 Food Pilot Plant",
    category: str = "Equipment",
    amount: str = "100.00",
    status: str | None = "Approved (SVP)",
) -> CommittedPRLine:
    return CommittedPRLine(
        pr_line_id=line_id,
        line_no=line_id,
        item_description=item,
        qty="1",
        unit_rate=amount,
        amount_gst=amount,
        currency_code="SGD",
        lab_name=lab,
        category_name=category,
        source_staging_line_id=None,
        pr_status=status,
    )


def _pr(
    pr_id: int,
    number: str = "PR-0001",
    requestor: str = "Tan Wei Ling",
    wbs: str = "W3-A",
    group: str = "FCB",
    total: str = "100.00",
    request_date: str | None = "2026-04-12",
    lines: list[CommittedPRLine] | None = None,
) -> CommittedPR:
    return CommittedPR(
        pr_id=pr_id,
        source_pr_number=number,
        requestor_name=requestor,
        purpose="Lab resupply",
        wbs_code=wbs,
        grand_total_sgd=total,
        lab_group_name=group,
        latest_batch_id=1,
        updated_at=datetime(2026, 9, 20, 11, 30),
        status="committed",
        pr_status="Approved (SVP)",
        request_date=request_date,
        lines=lines if lines is not None else [_line(pr_id)],
    )


def _meta() -> ReportMeta:
    return ReportMeta(
        generated_at=datetime(2026, 9, 22, 15, 4),
        generated_by_name="Test Admin",
        generated_by_email="admin@test.com",
        role_label="Admin",
        scope_label="All Lab Groups (Admin — full access)",
        fy_label="FY2026 (01 Apr 2026 – 31 Mar 2027)",
        date_range_label="Whole year",
        search_label="None",
        lab_group_label="All Lab Groups",
    )


def _header_row(ws) -> int:
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == HEADER_ROW_LABEL:
            return row
    raise AssertionError("data table header row not found")


def _load(prs: list[CommittedPR]):
    stream: BytesIO = build_pr_records_workbook(prs, _meta())
    return load_workbook(stream)


# ─── 2. Filter fidelity (mirrors RecordsPage.tsx filteredRecords) ────────
def test_search_matches_pr_number_case_insensitively() -> None:
    prs = [_pr(1, number="PR-00142"), _pr(2, number="PR-00999")]
    assert [p.pr_id for p in _apply_view_filters(prs, "pr-00142", "all")] == [1]


def test_search_matches_requestor_and_wbs() -> None:
    prs = [
        _pr(1, requestor="Nur Aisyah", wbs="W3-C"),
        _pr(2, requestor="Kumar Rajesh", wbs="ICT-1"),
    ]
    assert [p.pr_id for p in _apply_view_filters(prs, "aisyah", "all")] == [1]
    assert [p.pr_id for p in _apply_view_filters(prs, "ict-1", "all")] == [2]


def test_search_matches_nested_line_fields() -> None:
    """Item description, lab name and line status are all searchable."""
    prs = [
        _pr(1, lines=[_line(1, item="Benchtop centrifuge")]),
        _pr(2, lines=[_line(2, item="Reagent kit", lab="AI Robotics Lab")]),
        _pr(3, lines=[_line(3, item="Load cell", status="Pending Approval")]),
    ]
    assert [p.pr_id for p in _apply_view_filters(prs, "centrifuge", "all")] == [1]
    assert [p.pr_id for p in _apply_view_filters(prs, "robotics", "all")] == [2]
    assert [p.pr_id for p in _apply_view_filters(prs, "pending", "all")] == [3]


def test_empty_search_keeps_everything() -> None:
    prs = [_pr(1), _pr(2)]
    assert len(_apply_view_filters(prs, "   ", "all")) == 2


def test_lab_group_filter_uses_lowercased_name() -> None:
    """The dropdown's option value is the lowercased group name."""
    prs = [_pr(1, group="FCB"), _pr(2, group="ENG")]
    assert [p.pr_id for p in _apply_view_filters(prs, "", "fcb")] == [1]
    assert len(_apply_view_filters(prs, "", "all")) == 2


def test_lab_group_and_search_combine() -> None:
    prs = [
        _pr(1, group="FCB", requestor="Tan Wei Ling"),
        _pr(2, group="FCB", requestor="Nur Aisyah"),
        _pr(3, group="ENG", requestor="Tan Wei Ling"),
    ]
    result = _apply_view_filters(prs, "tan", "fcb")
    assert [p.pr_id for p in result] == [1]


def test_non_matching_search_yields_empty() -> None:
    assert _apply_view_filters([_pr(1)], "zzzznomatch", "all") == []


# ─── 3. Workbook shape ───────────────────────────────────────────────────
def test_workbook_has_both_sheets() -> None:
    wb = _load([_pr(1)])
    assert wb.sheetnames == ["PR Records", "Summary"]


def test_cover_block_reports_scope_and_filters() -> None:
    ws = _load([_pr(1)])["PR Records"]
    text = "\n".join(
        str(ws.cell(row=r, column=c).value)
        for r in range(1, _header_row(ws))
        for c in (1, 2)
    )
    assert "LAB BUDGET MONITORING SYSTEM" in text
    assert "admin@test.com" in text
    assert "All Lab Groups (Admin — full access)" in text
    assert "FY2026" in text


def test_one_row_per_line_not_per_pr() -> None:
    """A 3-line PR and a 1-line PR produce 4 data rows, not 2."""
    prs = [
        _pr(1, lines=[_line(1), _line(2), _line(3)]),
        _pr(2, number="PR-0002", lines=[_line(4)]),
    ]
    ws = _load(prs)["PR Records"]
    header = _header_row(ws)
    numbers = [ws.cell(row=r, column=1).value for r in range(header + 1, header + 5)]
    assert numbers == ["PR-0001", "PR-0001", "PR-0001", "PR-0002"]


def test_amounts_are_numeric_not_text() -> None:
    """Excel must be able to sum the amount column."""
    ws = _load([_pr(1, lines=[_line(1, amount="8988.00")])])["PR Records"]
    cell = ws.cell(row=_header_row(ws) + 1, column=14)
    assert isinstance(cell.value, (int, float))
    assert cell.value == pytest.approx(8988.00)
    assert cell.number_format == "#,##0.00"


def test_pr_date_written_as_real_date() -> None:
    ws = _load([_pr(1, request_date="2026-04-12")])["PR Records"]
    cell = ws.cell(row=_header_row(ws) + 1, column=2)
    assert cell.value == datetime(2026, 4, 12)
    assert cell.number_format == "dd mmm yyyy"


def test_missing_pr_date_is_blank_not_crash() -> None:
    ws = _load([_pr(1, request_date=None)])["PR Records"]
    assert ws.cell(row=_header_row(ws) + 1, column=2).value is None


def test_total_row_sums_all_lines() -> None:
    prs = [
        _pr(1, lines=[_line(1, amount="100.50"), _line(2, amount="200.25")]),
        _pr(2, number="PR-0002", lines=[_line(3, amount="99.25")]),
    ]
    ws = _load(prs)["PR Records"]
    total_row = _header_row(ws) + 4
    assert ws.cell(row=total_row, column=1).value == "TOTAL"
    assert ws.cell(row=total_row, column=14).value == pytest.approx(400.00)


def test_table_is_frozen_and_filterable() -> None:
    ws = _load([_pr(1)])["PR Records"]
    assert ws.freeze_panes == f"A{_header_row(ws) + 1}"
    assert "PRRecords" in ws.tables


def test_empty_result_still_produces_valid_workbook() -> None:
    """Exporting a filtered-to-nothing view must not blow up."""
    wb = _load([])
    ws = wb["PR Records"]
    header = _header_row(ws)
    assert "No PR records matched" in str(ws.cell(row=header + 1, column=1).value)
    assert ws.cell(row=header + 2, column=14).value == 0


def test_pr_with_no_visible_lines_still_appears() -> None:
    """A Lab IC view can hide every line of a PR; don't silently drop it."""
    ws = _load([_pr(1, total="500.00", lines=[])])["PR Records"]
    row = _header_row(ws) + 1
    assert ws.cell(row=row, column=1).value == "PR-0001"
    assert ws.cell(row=row, column=14).value == pytest.approx(500.00)


# ─── Summary sheet ───────────────────────────────────────────────────────
def test_summary_breaks_down_by_group_lab_category_status() -> None:
    ws = _load([_pr(1)])["Summary"]
    titles = {ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)}
    assert "Spending by Lab Group" in titles
    assert "Spending by Lab" in titles
    assert "Spending by Category" in titles
    assert "Spending by Line Status" in titles


def test_summary_totals_match_the_data_sheet() -> None:
    prs = [
        _pr(1, group="FCB", lines=[_line(1, amount="100.00")]),
        _pr(2, number="PR-0002", group="ENG", lines=[_line(2, amount="300.00")]),
    ]
    ws = _load(prs)["Summary"]
    for row in range(1, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "Total":
            assert ws.cell(row=row, column=4).value == pytest.approx(400.00)
            break
    else:
        raise AssertionError("no Total row found on the Summary sheet")


def test_summary_counts_distinct_prs_not_double_counted() -> None:
    """One PR spanning two categories is still ONE PR in the total row."""
    prs = [
        _pr(
            1,
            lines=[
                _line(1, category="Equipment", amount="100.00"),
                _line(2, category="Supplies", amount="100.00"),
            ],
        )
    ]
    ws = _load(prs)["Summary"]
    rows = [
        row
        for row in range(1, ws.max_row + 1)
        if ws.cell(row=row, column=1).value == "Spending by Category"
    ]
    category_block = rows[0]
    for row in range(category_block, ws.max_row + 1):
        if ws.cell(row=row, column=1).value == "Total":
            assert ws.cell(row=row, column=2).value == 1
            assert ws.cell(row=row, column=3).value == 2
            return
    raise AssertionError("no Total row in the category block")


# ─── Cover-label helpers ─────────────────────────────────────────────────
def test_date_range_label_prefers_custom_range() -> None:
    assert _date_range_label("90d", "2026-01-01", "2026-02-05") == (
        "Custom: 2026-01-01 to 2026-02-05"
    )
    assert _date_range_label("90d", "", "") == "Last 90 days"
    assert _date_range_label("all", "", "") == "Whole year"


def test_date_range_label_handles_open_ended_custom_range() -> None:
    assert _date_range_label("all", "2026-01-01", "") == ("Custom: 2026-01-01 to today")


def test_lab_group_label_is_not_applicable_for_non_admin() -> None:
    assert _lab_group_label([], "all", "teamlead") == "Not applicable for this role"
    assert _lab_group_label([], "all", "labic") == "Not applicable for this role"


def test_lab_group_label_recovers_original_casing() -> None:
    assert _lab_group_label([_pr(1, group="FCB")], "fcb", "admin") == "FCB"
    assert _lab_group_label([], "all", "admin") == "All Lab Groups"


# ─── 1. Role scoping (integration, against the real scoped query) ────────
def test_export_scoping_matches_list_scoping(db, admin_user) -> None:
    """
    The export must not widen access: for the same filters it returns exactly
    the PR set that /prs returns for that user.
    """
    from app.api.records import _scoped_committed_prs, _role_name

    role = _role_name(admin_user)
    listed = _scoped_committed_prs(db, admin_user, role, "all", None, None)
    exported = _scoped_committed_prs(db, admin_user, role, "all", None, None)
    assert [p.pr_id for p in listed] == [p.pr_id for p in exported]


def test_teamlead_without_group_exports_nothing(db) -> None:
    """A Team Lead with no lab_group_id must get an empty set, not everything."""
    from app.api.records import _scoped_committed_prs
    from app.models.auth import User

    orphan = User(
        role_id=1,
        full_name="Orphan Lead",
        email="orphan.lead@test.com",
        password_hash="x",
        lab_group_id=None,
    )
    assert _scoped_committed_prs(db, orphan, "teamlead", "all", None, None) == []


def test_labic_without_lab_exports_nothing(db) -> None:
    from app.api.records import _scoped_committed_prs
    from app.models.auth import User

    orphan = User(
        role_id=1,
        full_name="Orphan IC",
        email="orphan.ic@test.com",
        password_hash="x",
        lab_id=None,
    )
    assert _scoped_committed_prs(db, orphan, "labic", "all", None, None) == []


def test_date_bounds_are_applied(db, admin_user) -> None:
    """A window in the far past must exclude everything current."""
    from app.api.records import _scoped_committed_prs, _role_name

    role = _role_name(admin_user)
    result = _scoped_committed_prs(
        db, admin_user, role, "all", date(1990, 1, 1), date(1990, 12, 31)
    )
    assert result == []


# ─── HTTP-level RBAC (the requirement that actually matters) ─────────────
@pytest.fixture
def export_client(db):
    """
    TestClient wired to the rolled-back test session, with a swappable user.

    Overrides are removed on teardown so this file can't leak auth state into
    the rest of the suite.
    """
    from unittest.mock import MagicMock

    from fastapi.testclient import TestClient

    from app.database import get_db
    from app.dependencies.auth import get_current_user
    from app.main import app
    from app.models.auth import User

    state: dict[str, User] = {}

    def _as(role: str, lab_group_id=None, lab_id=None) -> None:
        state["user"] = User(
            user_id=999,
            email=f"{role}@test.com",
            full_name=f"Test {role}",
            role_id=1,
            role=MagicMock(role_name=role),
            lab_group_id=lab_group_id,
            lab_id=lab_id,
        )

    previous = dict(app.dependency_overrides)
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_current_user] = lambda: state["user"]
    client = TestClient(app)
    client.login_as = _as  # type: ignore[attr-defined]
    try:
        yield client
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


def _make_committed_pr(db, number: str, group_id: int, lab_id: int, category_id: int):
    """Insert a committed PR + one line directly (bypassing the commit flow)."""
    from app.models.staging import PurchaseRequest, PurchaseRequestLine

    pr = PurchaseRequest(
        source_pr_number=number,
        requestor_name="Export Tester",
        request_date=date(2026, 4, 12),
        purpose="Export scoping test",
        wbs_code="WBS-EXPORT",
        grand_total_sgd="500.00",
        lab_group_id=group_id,
        pr_status="Approved (SVP)",
    )
    db.add(pr)
    db.flush()
    db.add(
        PurchaseRequestLine(
            pr_id=pr.pr_id,
            line_no=1,
            item_description=f"Item for {number}",
            qty="1",
            unit_rate="500.00",
            amount_gst="500.00",
            currency_code="SGD",
            lab_id=lab_id,
            category_id=category_id,
            pr_status="Approved (SVP)",
        )
    )
    db.flush()
    return pr


def _sheet_text(response) -> str:
    wb = load_workbook(BytesIO(response.content))
    ws = wb["PR Records"]
    return "\n".join(
        str(ws.cell(row=r, column=c).value)
        for r in range(1, ws.max_row + 1)
        for c in range(1, 16)
    )


def _two_groups(db):
    """Two seeded lab groups that each have a lab, or skip."""
    from app.models.config import Lab, LabGroup, SpendingCategory

    pairs = []
    for group in (
        db.query(LabGroup)
        .filter(LabGroup.lab_group_name != "General")
        .order_by(LabGroup.lab_group_id)
        .all()
    ):
        lab = db.query(Lab).filter(Lab.lab_group_id == group.lab_group_id).first()
        if lab is not None:
            pairs.append((group, lab))
        if len(pairs) == 2:
            break
    if len(pairs) < 2:
        pytest.skip("Need two seeded lab groups with labs; run dev_seed.sql.")
    category = db.query(SpendingCategory).first()
    return pairs, category.category_id


def test_export_returns_a_real_xlsx_download(db, export_client) -> None:
    pairs, category_id = _two_groups(db)
    group_a, lab_a = pairs[0]
    _make_committed_pr(
        db, "PR-EXP-001", group_a.lab_group_id, lab_a.lab_id, category_id
    )

    export_client.login_as("admin")
    response = export_client.get("/api/records/export")

    assert response.status_code == 200
    assert response.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    assert "attachment" in response.headers["content-disposition"]
    assert ".xlsx" in response.headers["content-disposition"]
    assert "PR-EXP-001" in _sheet_text(response)


def test_teamlead_export_excludes_other_groups(db, export_client) -> None:
    """The headline requirement: a Team Lead's file holds only their group."""
    pairs, category_id = _two_groups(db)
    (group_a, lab_a), (group_b, lab_b) = pairs
    _make_committed_pr(
        db, "PR-MINE-001", group_a.lab_group_id, lab_a.lab_id, category_id
    )
    _make_committed_pr(
        db, "PR-THEIRS-001", group_b.lab_group_id, lab_b.lab_id, category_id
    )

    export_client.login_as("teamlead", lab_group_id=group_a.lab_group_id)
    text = _sheet_text(export_client.get("/api/records/export"))

    assert "PR-MINE-001" in text
    assert "PR-THEIRS-001" not in text
    assert "Team Lead scope" in text


def test_admin_export_includes_every_group(db, export_client) -> None:
    pairs, category_id = _two_groups(db)
    (group_a, lab_a), (group_b, lab_b) = pairs
    _make_committed_pr(
        db, "PR-MINE-002", group_a.lab_group_id, lab_a.lab_id, category_id
    )
    _make_committed_pr(
        db, "PR-THEIRS-002", group_b.lab_group_id, lab_b.lab_id, category_id
    )

    export_client.login_as("admin")
    text = _sheet_text(export_client.get("/api/records/export"))

    assert "PR-MINE-002" in text
    assert "PR-THEIRS-002" in text
    assert "Admin — full access" in text


def test_labic_export_scoped_to_own_lab(db, export_client) -> None:
    pairs, category_id = _two_groups(db)
    (group_a, lab_a), (group_b, lab_b) = pairs
    _make_committed_pr(db, "PR-LAB-A", group_a.lab_group_id, lab_a.lab_id, category_id)
    _make_committed_pr(db, "PR-LAB-B", group_b.lab_group_id, lab_b.lab_id, category_id)

    export_client.login_as("labic", lab_id=lab_a.lab_id)
    text = _sheet_text(export_client.get("/api/records/export"))

    assert "PR-LAB-A" in text
    assert "PR-LAB-B" not in text
    assert "Lab IC scope" in text


def test_export_honours_the_search_filter(db, export_client) -> None:
    pairs, category_id = _two_groups(db)
    (group_a, lab_a), _ = pairs
    _make_committed_pr(
        db, "PR-FIND-ME", group_a.lab_group_id, lab_a.lab_id, category_id
    )
    _make_committed_pr(
        db, "PR-HIDE-ME", group_a.lab_group_id, lab_a.lab_id, category_id
    )

    export_client.login_as("admin")
    text = _sheet_text(export_client.get("/api/records/export?search=FIND-ME"))

    assert "PR-FIND-ME" in text
    assert "PR-HIDE-ME" not in text


def test_export_rejects_unknown_role(db, export_client) -> None:
    export_client.login_as("vendor")
    assert export_client.get("/api/records/export").status_code == 403
