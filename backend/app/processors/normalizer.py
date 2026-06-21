from decimal import Decimal, InvalidOperation
import re


def normalize_text(value: object) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() in {"nan", "nat", "none"}:
        return ""
    return re.sub(r"\s+", " ", text)


def normalize_key_part(value: object) -> str:
    return normalize_text(value).casefold()


def parse_decimal(value: object) -> Decimal | None:
    text = normalize_text(value)
    if not text:
        return None
    cleaned = text.replace("$", "").replace(",", "")
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return None
