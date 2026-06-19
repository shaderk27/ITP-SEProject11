from __future__ import annotations

from uuid import uuid4
from sqlalchemy.orm import Session
import dataclasses
import inspect

from app.models.upload import UploadMetadata
from app.processors.upload_parser import (
    parse_line_items,
    read_upload_dataframe,
    validate_dataframe,
)
from app.repositories.upload_repository import UploadRepository
from app.services.duplicate_service import DuplicateService
from app.processors.classifier import classify_line_item

import app.models.config as config_models

# Dynamically hook into the exact class names Harry used
Lab = getattr(config_models, "Lab", None)
LabGroup = getattr(config_models, "LabGroup", None)
if not LabGroup:
    for name, cls in inspect.getmembers(config_models, inspect.isclass):
        if "group" in name.lower() and name.lower() != "lab":
            LabGroup = cls
            break

class UploadService:
    def __init__(
        self,
        repository: UploadRepository,
        duplicate_service: DuplicateService | None = None,
        db: Session | None = None, 
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
        except Exception as error:
            return self._failed_result(metadata, [{"field": "File", "message": f"Format error: {error}", "severity": "error"}])

        validation_errors = validate_dataframe(dataframe)
        if any(error["severity"] == "error" for error in validation_errors):
            return self._failed_result(metadata, validation_errors)

        line_items = parse_line_items(dataframe)
        store = self.repository.load_store()
        self.repository.save_batch_metadata(metadata, store)

        records = {"inserted": [], "updated": [], "duplicate": []}
        needs_review_count = 0
        
        # =========================================================
        # SCHEMA-PERFECT CACHE BUILDER 
        # =========================================================
        lab_cache = {}
        if self.db and Lab:
            all_labs = self.db.query(Lab).all()
            
            group_dict = {}
            if LabGroup:
                try:
                    for g in self.db.query(LabGroup).all():
                        g_id = getattr(g, "lab_group_id", None)
                        g_name = getattr(g, "lab_group_name", "Pending Lab Group")
                        if g_id is not None:
                            group_dict[g_id] = g_name
                except Exception as e:
                    pass
            
            for l in all_labs:
                group_name = "Pending Lab Group"
                fk_id = getattr(l, "lab_group_id", None)
                if fk_id is not None and fk_id in group_dict:
                    group_name = group_dict[fk_id]

                l_id = getattr(l, "lab_id", None)
                if l_id is not None:
                    lab_cache[l_id] = {
                        "lab_name": getattr(l, "lab_name", "Unknown Lab"),
                        "lab_group_name": group_name
                    }
        # =========================================================

        for item in line_items:
            assigned_lab = "Unassigned Lab"
            assigned_group = "Pending Lab Group"
            
            if self.db:
                item_dict = item.to_dict() if hasattr(item, "to_dict") else getattr(item, "__dict__", {})
                row_text = " ".join([str(v) for v in item_dict.values() if v is not None]).lower()
                
                req_name = ""
                for key, val in item_dict.items():
                    if str(key).lower() in ['requester', 'requestor', 'requester_name', 'requested_by', 'buyer']:
                        if val and isinstance(val, str):
                            req_name = val
                            break

                classification = classify_line_item(self.db, row_text, req_name)
                lab_id = classification.get("lab_id")
                
                if lab_id and lab_id in lab_cache:
                    assigned_lab = lab_cache[lab_id]["lab_name"]
                    assigned_group = lab_cache[lab_id]["lab_group_name"]
            
            # 1. Update the internal dataclass safely
            update_kwargs = {"lab": assigned_lab}
            if hasattr(item, "lab_group"): update_kwargs["lab_group"] = assigned_group
            if hasattr(item, "lab_group_name"): update_kwargs["lab_group_name"] = assigned_group

            # ==========================================
            # FORCE INJECTION (No more silent skipping)
            # ==========================================
            if dataclasses.is_dataclass(item):
                # We are forcing Python to inject lab_group. 
                # If PRLineItem in upload.py doesn't have it, this will intentionally crash!
                item = dataclasses.replace(item, lab=assigned_lab, lab_group=assigned_group)
            else:
                item.lab = assigned_lab
                item.lab_group = assigned_group
            
            if assigned_lab == "Unassigned Lab" or not assigned_lab:
                needs_review_count += 1
            # ==========================================

            existing = self.repository.get_line_record(item.line_identity_key, store)
            decision = self.duplicate_service.decide(item, existing)
            
            # 2. Extract the payload for the UI
            if hasattr(item, "to_dict"):
                final_line_dict = item.to_dict()
            elif dataclasses.is_dataclass(item):
                final_line_dict = dataclasses.asdict(item)
            else:
                final_line_dict = getattr(item, "__dict__", {}).copy()

            # 3. THE UI INJECTION: Force-feed the frontend in every format!
            final_line_dict["lab_group"] = assigned_group
            final_line_dict["labGroup"] = assigned_group
            final_line_dict["lab_group_name"] = assigned_group
            
            records[decision.status].append({
                "status": decision.status,
                "reason": decision.reason,
                "line": final_line_dict,
                "previous_batch_id": (None if existing is None else existing.get("batch_id")),
            })
            
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

    def _failed_result(self, metadata: UploadMetadata, errors: list[dict[str, str]]) -> dict:
        return {"success": False, "metadata": metadata.to_dict(), "counts": {"total_lines": 0, "accepted": 0, "duplicate_skipped": 0, "reupload_updated": 0, "needs_review": 0, "rejected": len(errors)}, "validation_errors": errors, "records": {"inserted": [], "updated": [], "duplicate": []}}