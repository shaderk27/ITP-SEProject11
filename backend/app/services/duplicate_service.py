from dataclasses import dataclass

from app.models.upload import PRLineItem


@dataclass(frozen=True)
class DuplicateDecision:
    status: str
    reason: str


class DuplicateService:
    def decide(
        self, item: PRLineItem, existing_record: dict | None
    ) -> DuplicateDecision:
        if existing_record is None:
            return DuplicateDecision(status="inserted", reason="New line identity.")

        existing_hash = existing_record.get("content_hash")
        if existing_hash == item.content_hash:
            return DuplicateDecision(
                status="duplicate", reason="Same line identity and same content hash."
            )

        return DuplicateDecision(
            status="updated", reason="Same line identity with changed content."
        )
