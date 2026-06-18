from __future__ import annotations

from uuid import uuid4
from sqlalchemy.orm import Session
import dataclasses

from app.models.upload import UploadMetadata
from app.processors.upload_parser import (
    parse_line_items,
    read_upload_dataframe,
    validate_dataframe,
)
from app.repositories.upload_repository import UploadRepository
from app.services.duplicate_service import DuplicateService
from app.processors.classifier import classify_line_item  # W7-04 Real Engine
from app.models.config import Lab # For Lab Name lookup

class UploadService:
    def __init__(
        self,
        repository: UploadRepository,
        duplicate_service: DuplicateService | None = None,
        db: Session | None = None,  # INJECTED DB SESSION
    ) -> None:
        self.repository = repository
        self.duplicate_service = duplicate_service or DuplicateService()
        self.db = db

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
            return self._failed_result(
                metadata,
                [{"field": "File Format", "message": str(error), "severity": "error"}],
            )
        except Exception as error:
            return self._failed_result(
                metadata,
                [
                    {
                        "field": "File",
                        "message": f"Could not read upload: {error}",
                        "severity": "error",
                    }
                ],
            )

        validation_errors = validate_dataframe(dataframe)
        if any(error["severity"] == "error" for error in validation_errors):
            return self._failed_result(metadata, validation_errors)

        line_items = parse_line_items(dataframe)
        store = self.repository.load_store()
        self.repository.save_batch_metadata(metadata, store)

        records = {"inserted": [], "updated": [], "duplicate": []}
        needs_review_count = 0
        
        # --- W7-04 SETUP: Pre-fetch Lab Names ---
        lab_cache = {}
        if self.db:
            all_labs = self.db.query(Lab).all()
            for l in all_labs:
                lab_cache[l.lab_id] = l.lab_name
        # ----------------------------------------

        for item in line_items:
            assigned_lab = "Unassigned Lab"
            
            # --- W7-04 LIVE EXECUTION ---
            if self.db:
                # 1. THE FIX: Use Harry's built-in .to_dict() to unlock the data safely
                if hasattr(item, "to_dict"):
                    item_dict = item.to_dict()
                elif isinstance(item, dict):
                    item_dict = item
                else:
                    item_dict = getattr(item, "__dict__", {})

                # 2. Mash the unlocked text together into a single string
                row_text = " ".join([str(v) for v in item_dict.values() if v is not None]).lower()
                
                # 3. Case-insensitive search for the requestor's name
                req_name = ""
                for key, val in item_dict.items():
                    if str(key).lower() in ['requester', 'requestor', 'requester_name', 'requested_by', 'buyer']:
                        if val and isinstance(val, str):
                            req_name = val
                            break

                # 4. Classify!
                classification = classify_line_item(self.db, row_text, req_name)
                lab_id = classification.get("lab_id")
                
                if lab_id and lab_id in lab_cache:
                    assigned_lab = lab_cache[lab_id]
            # ----------------------------
            
            # Update the item object with the new classification safely
            if dataclasses.is_dataclass(item):
                item = dataclasses.replace(item, lab=assigned_lab)
            else:
                item.lab = assigned_lab
            
            if assigned_lab == "Unassigned Lab" or not assigned_lab:
                needs_review_count += 1

            # Harry's exact duplicate logic
            existing = self.repository.get_line_record(item.line_identity_key, store)
            decision = self.duplicate_service.decide(item, existing)
            records[decision.status].append(
                {
                    "status": decision.status,
                    "reason": decision.reason,
                    "line": item.to_dict() if hasattr(item, "to_dict") else item_dict,
                    "previous_batch_id": (
                        None if existing is None else existing.get("batch_id")
                    ),
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
                "needs_review": needs_review_count,  
                "rejected": 0,
            },
            "validation_errors": validation_errors,
            "records": records,
        }

    def _failed_result(
        self, metadata: UploadMetadata, errors: list[dict[str, str]]
    ) -> dict:
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