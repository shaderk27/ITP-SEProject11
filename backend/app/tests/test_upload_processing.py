from io import BytesIO
from pathlib import Path
import tempfile

import pandas as pd  # type: ignore[import-untyped]

from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService


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
