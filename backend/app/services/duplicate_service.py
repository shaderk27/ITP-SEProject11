from dataclasses import dataclass

from app.models.upload import PRLineItem


def _status_word(status: str | None) -> str:
    return (status or "").strip().lower()


def is_status_regression(
    accepted_status: str | None, incoming_status: str | None
) -> bool:
    """True when a committed Approved line would change to a non-Approved status.

    Approval is final: once the accepted status starts with "approved"
    (e.g. "Approved (SVP)"), Pending, Rejected, Cancelled, blank or any other
    status is refused. Another Approved variant may still replace it.
    """
    return _status_word(accepted_status).startswith("approved") and not _status_word(
        incoming_status
    ).startswith("approved")


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
