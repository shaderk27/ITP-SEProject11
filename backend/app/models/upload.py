from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal


@dataclass(frozen=True)
class UploadMetadata:
    batch_id: str
    filename: str
    uploader_email: str
    uploader_name: str
    uploader_role: str
    uploaded_at: str

    @classmethod
    def create(
        cls,
        *,
        batch_id: str,
        filename: str,
        uploader_email: str,
        uploader_name: str,
        uploader_role: str,
    ) -> "UploadMetadata":
        return cls(
            batch_id=batch_id,
            filename=filename,
            uploader_email=uploader_email,
            uploader_name=uploader_name,
            uploader_role=uploader_role,
            uploaded_at=datetime.now(UTC).isoformat(timespec="seconds"),
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PRLineItem:
    row_number: int
    pr_number: str
    pr_sub_date: str
    requestor: str
    purpose: str
    pr_status: str
    po_number: str
    po_status: str
    grand_total_sgd: Decimal | None
    item_details: str
    quantity: Decimal | None
    unit_rate: Decimal | None
    wbs: str
    instruction_to_vendor: str
    pr_category: str
    amount_gst: Decimal
    line_identity_key: str
    content_hash: str
    # Fields with default values MUST be at the end
    lab: str = "Unassigned Lab"
    lab_group: str = "Pending Lab Group"

    def to_dict(self) -> dict:
        data = asdict(self)
        for key in ("grand_total_sgd", "quantity", "unit_rate", "amount_gst"):
            value = data[key]
            data[key] = None if value is None else str(value)
        return data
