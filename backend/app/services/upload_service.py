from __future__ import annotations

import dataclasses
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

import app.models.config as config_models
from app.models.auth import User
from app.models.upload import UploadMetadata
from app.processors.classifier import classify_line_item
from app.processors.upload_parser import (
    parse_line_items,
    read_upload_dataframe,
    validate_dataframe,
)
from app.repositories.persistence_repository import persist_upload_to_db
from app.repositories.upload_repository import UploadRepository
from app.services.duplicate_service import DuplicateService

Lab = getattr(config_models, "Lab", None)
LabGroup = getattr(config_models, "LabGroup", None)
SpendingCategory = getattr(config_models, "SpendingCategory", None)


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
        current_user: User | None = None,
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
            return self._failed_result(
                metadata,
                [
                    {
                        "field": "File",
                        "message": f"Format error: {error}",
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

        records: dict[str, list[dict]] = {
            "inserted": [],
            "updated": [],
            "duplicate": [],
            "status_regression": [],
        }
        needs_review_count = 0

        # Lookups for classification mapping
        lab_cache: dict[int, dict[str, str]] = {}
        group_cache: dict[int, str] = {}
        category_cache: dict[int, str] = {}

        if self.db:
            try:
                if LabGroup:
                    for g in self.db.query(LabGroup).all():
                        g_id = getattr(g, "lab_group_id", None)
                        if g_id is not None:
                            group_cache[g_id] = getattr(
                                g, "lab_group_name", "Pending Lab Group"
                            )

                if Lab:
                    for lab in self.db.query(Lab).all():
                        group_name = "Pending Lab Group"
                        fk_id = getattr(lab, "lab_group_id", None)
                        if fk_id is not None and fk_id in group_cache:
                            group_name = group_cache[fk_id]

                        l_id = getattr(lab, "lab_id", None)
                        if l_id is not None:
                            lab_cache[l_id] = {
                                "lab_name": getattr(lab, "lab_name", "Unknown Lab"),
                                "lab_group_name": group_name,
                            }

                if SpendingCategory:
                    for c in self.db.query(SpendingCategory).all():
                        c_id = getattr(c, "category_id", None)
                        if c_id is not None:
                            category_cache[c_id] = getattr(
                                c, "category_name", "General"
                            )

            except Exception:
                pass

        classified_items: list[dict] = []

        for item in line_items:
            assigned_lab = "Unassigned Lab"
            assigned_group = "Pending Lab Group"
            assigned_category = "General"
            classification_reason = "Manual review required."

            classification: dict[str, Any] = {
                "lab_id": None,
                "lab_group_id": None,
                "category_id": None,
                "reason": classification_reason,
                "wbs_allocations": [],
            }

            raw_allocations = list(getattr(item, "wbs_allocations", ()) or ())
            enriched_allocations: list[dict[str, Any]] = []

            if self.db:
                try:
                    item_dict = (
                        item.to_dict()
                        if hasattr(item, "to_dict")
                        else getattr(item, "__dict__", {})
                    )
                    row_text = " ".join(
                        [
                            str(v)
                            for k, v in item_dict.items()
                            if v is not None and k != "wbs_allocations"
                        ]
                    ).lower()

                    classification = classify_line_item(
                        self.db,
                        row_text,
                        item_dict.get("requestor", ""),
                        wbs=item_dict.get("wbs", ""),
                        purpose=item_dict.get("purpose", ""),
                        instruction_to_vendor=item_dict.get(
                            "instruction_to_vendor", ""
                        ),
                        req_type=item_dict.get("req_type", ""),
                        pr_category=item_dict.get("pr_category", ""),
                    )

                    lab_id = classification.get("lab_id")
                    group_id = classification.get("lab_group_id")
                    cat_id = classification.get("category_id")
                    classification_reason = classification.get(
                        "reason", classification_reason
                    )

                    if lab_id and lab_id in lab_cache:
                        assigned_lab = lab_cache[lab_id]["lab_name"]
                        assigned_group = lab_cache[lab_id]["lab_group_name"]
                    elif group_id and group_id in group_cache:
                        assigned_group = group_cache[group_id]

                    if cat_id and cat_id in category_cache:
                        assigned_category = category_cache[cat_id]

                    # Classify each WBS allocation portion individually when multi-WBS is present
                    for alloc in raw_allocations:
                        alloc_wbs = str(alloc.get("wbs") or item_dict.get("wbs") or "")
                        alloc_cls = classify_line_item(
                            self.db,
                            f"{row_text} {alloc_wbs.lower()}",
                            item_dict.get("requestor", ""),
                            wbs=alloc_wbs,
                            purpose=item_dict.get("purpose", ""),
                            instruction_to_vendor=item_dict.get(
                                "instruction_to_vendor", ""
                            ),
                            req_type=item_dict.get("req_type", ""),
                            pr_category=item_dict.get("pr_category", ""),
                        )
                        a_lab_id = alloc_cls.get("lab_id")
                        a_group_id = alloc_cls.get("lab_group_id")
                        a_cat_id = alloc_cls.get("category_id")
                        a_lab_name = (
                            lab_cache[a_lab_id]["lab_name"]
                            if a_lab_id and a_lab_id in lab_cache
                            else "General"
                        )
                        a_group_name = (
                            lab_cache[a_lab_id]["lab_group_name"]
                            if a_lab_id and a_lab_id in lab_cache
                            else (
                                group_cache.get(a_group_id, "General")
                                if a_group_id
                                else "General"
                            )
                        )
                        a_cat_name = (
                            category_cache.get(a_cat_id, "General")
                            if a_cat_id
                            else "General"
                        )
                        enriched_allocations.append(
                            {
                                **alloc,
                                "suggested_lab_group_id": a_group_id,
                                "suggested_lab_group_name": a_group_name,
                                "suggested_lab_id": a_lab_id,
                                "suggested_lab_name": a_lab_name,
                                "suggested_category_id": a_cat_id,
                                "suggested_category_name": a_cat_name,
                                "reason": alloc_cls.get("reason", ""),
                            }
                        )

                except Exception:
                    classification_reason = (
                        "Classification unavailable. Manual review required."
                    )

            if not enriched_allocations and raw_allocations:
                enriched_allocations = [
                    {
                        **alloc,
                        "suggested_lab_group_id": classification.get("lab_group_id"),
                        "suggested_lab_group_name": assigned_group,
                        "suggested_lab_id": classification.get("lab_id"),
                        "suggested_lab_name": assigned_lab,
                        "suggested_category_id": classification.get("category_id"),
                        "suggested_category_name": assigned_category,
                        "reason": classification_reason,
                    }
                    for alloc in raw_allocations
                ]

            classification["wbs_allocations"] = enriched_allocations

            if dataclasses.is_dataclass(item):
                item = dataclasses.replace(
                    item,
                    lab=assigned_lab,
                    lab_group=assigned_group,
                    category=assigned_category,
                    wbs_allocations=tuple(enriched_allocations),
                )
            else:
                item.lab = assigned_lab
                item.lab_group = assigned_group
                item.category = assigned_category

            existing = self.repository.get_line_record(item.line_identity_key, store)
            decision = self.duplicate_service.decide(item, existing)

            if decision.status != "duplicate":
                if (
                    assigned_lab in ("Unassigned Lab", "General")
                    or not assigned_lab
                    or assigned_category == "General"
                    or len(enriched_allocations) > 1
                ):
                    needs_review_count += 1
                classified_items.append(
                    {
                        "item": item,
                        "classification": classification,
                        "duplicate_decision": decision.status,
                    }
                )

            if hasattr(item, "to_dict"):
                final_line_dict = item.to_dict()
            elif dataclasses.is_dataclass(item):
                final_line_dict = dataclasses.asdict(item)
            else:
                final_line_dict = getattr(item, "__dict__", {}).copy()

            final_line_dict["lab_group"] = assigned_group
            final_line_dict["labGroup"] = assigned_group
            final_line_dict["lab_group_name"] = assigned_group

            final_line_dict["category"] = assigned_category
            final_line_dict["pr_category"] = assigned_category
            final_line_dict["category_name"] = assigned_category

            final_line_dict["classification_reason"] = classification_reason

            records[decision.status].append(
                {
                    "status": decision.status,
                    "reason": decision.reason,
                    "line": final_line_dict,
                    "previous_batch_id": (
                        None if existing is None else existing.get("batch_id")
                    ),
                }
            )

            if decision.status in {"inserted", "updated"}:
                self.repository.upsert_line_record(item, metadata, store)

        self.repository.save_store(store)

        persistence_counts: dict = {}
        if self.db and current_user and classified_items:
            persistence_counts = persist_upload_to_db(
                db=self.db,
                metadata=metadata,
                classified_items=classified_items,
                current_user=current_user,
            )
            needs_review_count = persistence_counts.get(
                "queue_items_inserted", needs_review_count
            )
            self._move_status_regressions(
                records, persistence_counts.pop("status_regression_rows", {})
            )
            self._attach_review_issues(
                records, persistence_counts.pop("review_issues", {})
            )

        return {
            "success": True,
            "metadata": metadata.to_dict(),
            "persistence": persistence_counts,
            "counts": {
                "total_lines": len(line_items),
                "accepted": len(records["inserted"]),
                "duplicate_skipped": len(records["duplicate"]),
                "reupload_updated": len(records["updated"]),
                "needs_review": needs_review_count,
                "rejected": 0,
                "status_regressions_skipped": len(records["status_regression"]),
            },
            "validation_errors": [],
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
                "status_regressions_skipped": 0,
            },
            "validation_errors": errors,
            "records": {
                "inserted": [],
                "updated": [],
                "duplicate": [],
                "status_regression": [],
            },
        }

    @staticmethod
    def _attach_review_issues(
        records: dict[str, list[dict]], issue_by_row: dict[int, str]
    ) -> None:
        """Give the summary the same review message the queue stores."""
        for bucket in ("inserted", "updated"):
            for record in records[bucket]:
                issue = issue_by_row.get(record["line"].get("row_number"))
                if issue:
                    record["line"]["review_issue"] = issue

    @staticmethod
    def _move_status_regressions(
        records: dict[str, list[dict]], accepted_by_row: dict[int, str]
    ) -> None:
        """Re-bucket rows the DB check says commit will skip (W17), so the
        summary doesn't list them as accepted or updated."""
        for bucket in ("inserted", "updated"):
            kept = []
            for record in records[bucket]:
                accepted = accepted_by_row.get(record["line"].get("row_number"))
                if accepted is None:
                    kept.append(record)
                    continue
                record["status"] = "status_regression"
                incoming = record["line"].get("pr_status") or "a blank status"
                record["reason"] = (
                    f"Already {accepted} in final records; this file says "
                    f"{incoming}. Approved status is final, so this line is "
                    "skipped at commit."
                )
                records["status_regression"].append(record)
            records[bucket] = kept
        records["status_regression"].sort(key=lambda r: r["line"].get("row_number", 0))
