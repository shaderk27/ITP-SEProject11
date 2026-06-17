from io import BytesIO
from pathlib import Path
import tempfile

import pandas as pd

from app.repositories.upload_repository import UploadRepository
from app.services.upload_service import UploadService


def _sample_csv(amount: str = "650.00") -> bytes:
    data = pd.DataFrame(
        [
            {
                "PR": "PR-2026-1525",
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
