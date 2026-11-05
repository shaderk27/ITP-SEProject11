from io import BytesIO
from pathlib import Path
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile
from decimal import Decimal

import pandas as pd  # type: ignore[import-untyped]

from app.repositories.upload_repository import UploadRepository
from app.repositories.persistence_repository import _resolve_line_amount
from app.processors.upload_parser import (
    parse_line_items,
    read_upload_dataframe,
    validate_dataframe,
)
from app.services.upload_service import UploadService


STRICT_NAMESPACES = {
    b"http://schemas.openxmlformats.org/spreadsheetml/2006/main": (
        b"http://purl.oclc.org/ooxml/spreadsheetml/main"
    ),
    b"http://schemas.openxmlformats.org/officeDocument/2006/relationships": (
        b"http://purl.oclc.org/ooxml/officeDocument/relationships"
    ),
}


def _sample_csv(amount: str = "650.00") -> bytes:
    data = pd.DataFrame(
        [
            {
                "PR": "PR-2026-1525",
                "PR Status": "Pending",
                "PO": "",
                "PO Status": "",
                "PR Sub Date": "2026-05-18",
                "Requestor": "Sarah Chen",
                "Purpose": "Workshop materials",
                "Grand Total in SGD": "650.00",
                "Item Details": "Miscellaneous supplies",
                "Qty": "10",
                "Unit Rate": "65.00",
                "WBS": "MISC-001",
                "Instruction to Vendor": "Deliver to W3",
                "PR Category": "Consumables",
                "Lab": "General",
                "Amount + GST": amount,
            }
        ]
    )
    buffer = BytesIO()
    data.to_csv(buffer, index=False)
    return buffer.getvalue()


def _fy2025_style_csv() -> bytes:
    data = pd.DataFrame(
        [
            {
                "PR": "PR2500000008",
                "PO": "1000048709",
                "PR Status": "Approved (SVP)",
                "PO Status": "COMP",
                "PR Sub Date": "2026-04-01",
                "Requestor": "azzalia.abu",
                "Purpose": "Move ultrasound system",
                "Grand Total in SGD": "850.00",
                "Item Details": "TRANSPORTATION",
                "Qty": "1",
                "Unit Rate": "350.00",
                "WBS": "D-MOE-A204-E004-OOE",
                "Instruction to Vendor": "Deliver to Punggol",
            }
        ]
    )
    buffer = BytesIO()
    data.to_csv(buffer, index=False)
    return buffer.getvalue()


def _strict_xlsx_with_continuation_row() -> bytes:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR2600002605",
                "PR Status": "Approved (SVP)",
                "PR Sub Date": "2026-09-07",
                "Requestor": "mingze.chai",
                "Purpose": "Carbonation consumables",
                "Grand Total in SGD": "70.00",
                "Item Details": "PURE CO2 30KG",
                "Qty": "1",
                "Unit Rate": "60.00",
                "WBS": "A-ASTAR-CTIL-0001-OOE",
            },
            {
                "PR": None,
                "PR Status": None,
                "PR Sub Date": None,
                "Requestor": None,
                "Purpose": None,
                "Grand Total in SGD": None,
                "Item Details": "TRANSPORT CHARGES",
                "Qty": "1",
                "Unit Rate": "10.00",
                "WBS": "A-ASTAR-CTIL-0001-OOE",
            },
            {
                "PR": None,
                "PR Status": None,
                "PR Sub Date": None,
                "Requestor": None,
                "Purpose": None,
                "Grand Total in SGD": None,
                "Item Details": None,
                "Qty": None,
                "Unit Rate": None,
                "WBS": "A-ASTAR-CTIL-0001-OOE",
            },
        ]
    )
    standard = BytesIO()
    dataframe.to_excel(standard, index=False)
    standard.seek(0)

    strict = BytesIO()
    with ZipFile(standard) as source, ZipFile(strict, "w", ZIP_DEFLATED) as output:
        for member in source.infolist():
            data = source.read(member.filename)
            if member.filename.endswith((".xml", ".rels")):
                for standard_uri, strict_uri in STRICT_NAMESPACES.items():
                    data = data.replace(standard_uri, strict_uri)
            output.writestr(member, data)
    return strict.getvalue()


def _html_xls_with_continuation_row() -> bytes:
    headers = [
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
    rows = [
        [
            "PR2600002605",
            "Approved (SVP)",
            "07-09-2026",
            "mingze.chai",
            "Carbonation consumables",
            "70.00",
            "PURE CO2 30KG",
            "1",
            "60.00",
            "A-ASTAR-CTIL-0001-OOE",
        ],
        [
            "",
            "",
            "",
            "",
            "",
            "",
            "TRANSPORT CHARGES",
            "1",
            "10.00",
            "A-ASTAR-CTIL-0001-OOE",
        ],
        ["", "", "", "", "", "", "", "", "", "A-ASTAR-CTIL-0001-OOE"],
    ]
    header_html = "".join(f"<td>{value}</td>" for value in headers)
    row_html = "".join(
        f"<tr>{''.join(f'<td>{value}</td>' for value in row)}</tr>" for row in rows
    )
    return f"<table><tr>{header_html}</tr>{row_html}</table>".encode("utf-16")


def test_duplicate_and_reupload_detection() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = UploadRepository(Path(directory) / "store.json")
        service = UploadService(repo)

        first = service.process_upload(
            filename="sample.csv",
            content=_sample_csv("650.00"),
            uploader_email="lead@sit.edu.sg",
            uploader_name="Lead",
            uploader_role="teamlead",
        )
        duplicate = service.process_upload(
            filename="sample.csv",
            content=_sample_csv("650.00"),
            uploader_email="lead@sit.edu.sg",
            uploader_name="Lead",
            uploader_role="teamlead",
        )
        updated = service.process_upload(
            filename="sample.csv",
            content=_sample_csv("700.00"),
            uploader_email="lead@sit.edu.sg",
            uploader_name="Lead",
            uploader_role="teamlead",
        )

    assert first["counts"]["accepted"] == 1
    assert duplicate["counts"]["duplicate_skipped"] == 1
    assert updated["counts"]["reupload_updated"] == 1


def test_fy2025_export_format_derives_amount_and_preserves_status() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = UploadRepository(Path(directory) / "store.json")
        service = UploadService(repo)

        result = service.process_upload(
            filename="fy2025.csv",
            content=_fy2025_style_csv(),
            uploader_email="admin@sit.edu.sg",
            uploader_name="Admin",
            uploader_role="admin",
        )

    line = result["records"]["inserted"][0]["line"]

    assert result["success"] is True
    assert result["counts"]["accepted"] == 1
    assert result["validation_errors"] == []
    assert line["pr_status"] == "Approved (SVP)"
    assert line["po_number"] == "1000048709"
    assert line["po_status"] == "COMP"
    assert line["amount_gst"] == "350.00"


def test_strict_xlsx_expands_pr_headers_and_ignores_formatting_rows() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = UploadRepository(Path(directory) / "store.json")
        service = UploadService(repo)

        result = service.process_upload(
            filename="strict-export.xlsx",
            content=_strict_xlsx_with_continuation_row(),
            uploader_email="admin@sit.edu.sg",
            uploader_name="Admin",
            uploader_role="admin",
        )

    lines = [record["line"] for record in result["records"]["inserted"]]
    assert result["success"] is True
    assert result["counts"]["accepted"] == 2
    assert [line["pr_number"] for line in lines] == ["PR2600002605"] * 2
    assert [line["amount_gst"] for line in lines] == ["60.00", "10.00"]


def test_html_xls_export_is_supported() -> None:
    with tempfile.TemporaryDirectory() as directory:
        repo = UploadRepository(Path(directory) / "store.json")
        service = UploadService(repo)

        result = service.process_upload(
            filename="source-export.xls",
            content=_html_xls_with_continuation_row(),
            uploader_email="admin@sit.edu.sg",
            uploader_name="Admin",
            uploader_role="admin",
        )

    assert result["success"] is True
    assert result["counts"]["accepted"] == 2


def test_new_pr_does_not_inherit_blank_required_fields_or_po() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR1",
                "PO": "1000057916",
                "PR Status": "Approved",
                "PO Status": "OPEN",
                "PR Sub Date": "2026-05-01",
                "Requestor": "alice",
                "Purpose": "First purchase",
                "Grand Total in SGD": "10",
                "Item Details": "First item",
                "Qty": "1",
                "Unit Rate": "10",
                "WBS": "WBS-1",
            },
            {
                "PR": "PR2",
                "PO": "",
                "PR Status": "Rejected",
                "PO Status": "",
                "PR Sub Date": "2026-05-02",
                "Requestor": "",
                "Purpose": "Second purchase",
                "Grand Total in SGD": "20",
                "Item Details": "Second item",
                "Qty": "1",
                "Unit Rate": "20",
                "WBS": "WBS-2",
            },
        ]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False)

    prepared = read_upload_dataframe("new-pr.xlsx", buffer.getvalue())
    errors = validate_dataframe(prepared)

    assert pd.isna(prepared.iloc[1]["Requestor"])
    assert pd.isna(prepared.iloc[1]["PO"])
    assert any(error["field"] == "Row 3 - Requestor" for error in errors)


def test_numeric_po_is_stable_and_blank_po_does_not_leak() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR1",
                "PO": 1000055022,
                "PR Status": "Approved",
                "PO Status": "OPEN",
                "PR Sub Date": "2026-05-01",
                "Requestor": "alice",
                "Purpose": "First purchase",
                "Grand Total in SGD": 10,
                "Item Details": "First item",
                "Qty": 1,
                "Unit Rate": 10,
                "WBS": "WBS-1",
            },
            {
                "PR": "PR2",
                "PO": None,
                "PR Status": "Rejected",
                "PO Status": None,
                "PR Sub Date": "2026-05-02",
                "Requestor": "bob",
                "Purpose": "Second purchase",
                "Grand Total in SGD": 20,
                "Item Details": "Second item",
                "Qty": 1,
                "Unit Rate": 20,
                "WBS": "WBS-2",
            },
        ]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False)
    csv_buffer = BytesIO()
    dataframe.to_csv(csv_buffer, index=False)

    prepared = read_upload_dataframe("numeric-po.xlsx", buffer.getvalue())
    lines = parse_line_items(prepared)
    csv_lines = parse_line_items(
        read_upload_dataframe("numeric-po.csv", csv_buffer.getvalue())
    )

    assert lines[0].po_number == "1000055022"
    assert lines[1].po_number == ""
    assert [line.content_hash for line in lines] == [
        line.content_hash for line in csv_lines
    ]


def test_repeated_identical_lines_are_distinct_and_duplicate_on_reupload() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR-DUP",
                "PR Status": "Approved",
                "PR Sub Date": "2026-05-01",
                "Requestor": "alice",
                "Purpose": "Repeated supplies",
                "Grand Total in SGD": "20",
                "Item Details": "Identical item",
                "Qty": "1",
                "Unit Rate": "10",
                "WBS": "WBS-1",
            },
            {
                "PR": "",
                "PR Status": "",
                "PR Sub Date": "",
                "Requestor": "",
                "Purpose": "",
                "Grand Total in SGD": "",
                "Item Details": "Identical item",
                "Qty": "1",
                "Unit Rate": "10",
                "WBS": "WBS-1",
            },
        ]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False)
    content = buffer.getvalue()

    with tempfile.TemporaryDirectory() as directory:
        service = UploadService(UploadRepository(Path(directory) / "store.json"))
        first = service.process_upload(
            filename="repeated.xlsx",
            content=content,
            uploader_email="admin@sit.edu.sg",
            uploader_name="Admin",
            uploader_role="admin",
        )
        second = service.process_upload(
            filename="repeated.xlsx",
            content=content,
            uploader_email="admin@sit.edu.sg",
            uploader_name="Admin",
            uploader_role="admin",
        )

    identities = [
        record["line"]["line_identity_key"] for record in first["records"]["inserted"]
    ]
    assert first["counts"]["accepted"] == 2
    assert len(set(identities)) == 2
    assert identities[1].endswith("::occurrence_2")
    assert second["counts"]["duplicate_skipped"] == 2


def test_foreign_currency_lines_reconcile_to_sgd_total() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR-USD",
                "PR Status": "Approved",
                "PR Sub Date": "2026-05-01",
                "Requestor": "alice",
                "Purpose": "Imported equipment",
                "Grand Total in SGD": "40.50",
                "Curr": "USD",
                "Item Details": "Part A",
                "Qty": "1",
                "Unit Rate": "10",
                "WBS": "WBS-1",
            },
            {
                "PR": "",
                "PR Status": "",
                "PR Sub Date": "",
                "Requestor": "",
                "Purpose": "",
                "Grand Total in SGD": "",
                "Curr": "",
                "Item Details": "Part B",
                "Qty": "2",
                "Unit Rate": "10",
                "WBS": "WBS-1",
            },
        ]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False)

    prepared = read_upload_dataframe("usd.xlsx", buffer.getvalue())
    lines = parse_line_items(prepared)

    assert [line.source_currency for line in lines] == ["USD", "USD"]
    assert [line.source_amount for line in lines] == [Decimal("10"), Decimal("20")]
    assert [line.amount_gst for line in lines] == [Decimal("13.50"), Decimal("27.00")]
    assert sum((line.amount_gst for line in lines), Decimal("0")) == Decimal("40.50")


def test_zero_value_line_does_not_fall_back_to_pr_total() -> None:
    dataframe = pd.DataFrame(
        [
            {
                "PR": "PR-FREE",
                "PR Status": "Approved",
                "PR Sub Date": "2026-05-01",
                "Requestor": "alice",
                "Purpose": "Free sample",
                "Grand Total in SGD": "100",
                "Item Details": "Complimentary item",
                "Qty": "1",
                "Unit Rate": "0",
                "WBS": "WBS-1",
            }
        ]
    )
    buffer = BytesIO()
    dataframe.to_excel(buffer, index=False)

    line = parse_line_items(read_upload_dataframe("free-item.xlsx", buffer.getvalue()))[
        0
    ]

    assert line.amount_gst == Decimal("0.00")
    assert _resolve_line_amount(line) == Decimal("0.00")
