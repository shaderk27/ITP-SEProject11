from __future__ import annotations

from uuid import uuid4

from app.models.upload import UploadMetadata
from app.processors.upload_parser import parse_line_items, read_upload_dataframe, validate_dataframe
from app.repositories.upload_repository import UploadRepository
from app.services.duplicate_service import DuplicateService


class UploadService:
    def __init__(self, repository: UploadRepository, duplicate_service: DuplicateService | None = None) -> None:
        self.repository = repository
        self.duplicate_service = duplicate_service or DuplicateService()

    def process_upload(
        self,
        *,
        filename: str,
        content: bytes,
        uploader_email: str,
        uploader_name: str,
        uploader_role: str,
    ) -> dict:
        batch_id = f"UP-{uuid4().hex[:8].upper()}"
        metadata = UploadMetadata.create(
            batch_id=batch_id,
            filename=filename,
            uploader_email=uploader_email,
            uploader_name=uploader_name,
            uploader_role=uploader_role,
        )

        try:
            dataframe = read_upload_dataframe(filename, content)
        except ValueError as error:
            return self._failed_result(metadata, [{"field": "File Format", "message": str(error), "severity": "error"}])
        except Exception as error:
            return self._failed_result(metadata, [{"field": "File", "message": f"Could not read upload: {error}", "severity": "error"}])

        validation_errors = validate_dataframe(dataframe)
        if any(error["severity"] == "error" for error in validation_errors):
            return self._failed_result(metadata, validation_errors)

        line_items = parse_line_items(dataframe)
        store = self.repository.load_store()
        self.repository.save_batch_metadata(metadata, store)

        records = {"inserted": [], "updated": [], "duplicate": []}
        for item in line_items:
            existing = self.repository.get_line_record(item.line_identity_key, store)
            decision = self.duplicate_service.decide(item, existing)
            records[decision.status].append(
                {
                    "status": decision.status,
                    "reason": decision.reason,
                    "line": item.to_dict(),
                    "previous_batch_id": None if existing is None else existing.get("batch_id"),
                }
            )
            if decision.status in {"inserted", "updated"}:
                self.repository.upsert_line_record(item, metadata, store)

        self.repository.save_store(store)

        return {
            "success": True,
            "metadata": metadata.to_dict(),
            "counts": {
                "total_lines": len(line_items),
                "accepted": len(records["inserted"]),
                "duplicate_skipped": len(records["duplicate"]),
                "reupload_updated": len(records["updated"]),
                "needs_review": 0,
                "rejected": 0,
            },
            "validation_errors": validation_errors,
            "records": records,
        }

    def _failed_result(self, metadata: UploadMetadata, errors: list[dict[str, str]]) -> dict:
        return {
            "success": False,
            "metadata": metadata.to_dict(),
            "counts": {
                "total_lines": 0,
                "accepted": 0,
                "duplicate_skipped": 0,
                "reupload_updated": 0,
                "needs_review": 0,
                "rejected": len(errors),
            },
            "validation_errors": errors,
            "records": {"inserted": [], "updated": [], "duplicate": []},
        }
