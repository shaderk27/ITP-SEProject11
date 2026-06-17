from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.models.upload import PRLineItem, UploadMetadata


class UploadRepository:
    def __init__(self, storage_path: Path | None = None) -> None:
        backend_root = Path(__file__).resolve().parents[2]
        self.storage_path = storage_path or backend_root / ".data" / "upload_store.json"

    def load_store(self) -> dict[str, Any]:
        if not self.storage_path.exists():
            return {"batches": [], "line_records": {}}
        with self.storage_path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def save_store(self, store: dict[str, Any]) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        with self.storage_path.open("w", encoding="utf-8") as file:
            json.dump(store, file, indent=2)

    def save_batch_metadata(
        self, metadata: UploadMetadata, store: dict[str, Any]
    ) -> None:
        store.setdefault("batches", []).append(metadata.to_dict())

    def get_line_record(
        self, identity_key: str, store: dict[str, Any]
    ) -> dict[str, Any] | None:
        return store.setdefault("line_records", {}).get(identity_key)

    def upsert_line_record(
        self, item: PRLineItem, metadata: UploadMetadata, store: dict[str, Any]
    ) -> None:
        store.setdefault("line_records", {})[item.line_identity_key] = {
            "batch_id": metadata.batch_id,
            "last_uploaded_at": metadata.uploaded_at,
            "filename": metadata.filename,
            "content_hash": item.content_hash,
            "line_item": item.to_dict(),
        }
