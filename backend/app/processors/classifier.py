import re

from sqlalchemy.orm import Session

from app.models.config import Lab, LabGroup, RequesterLabMapping

STOP_WORDS = {
    "lab",
    "laboratory",
    "system",
    "systems",
    "room",
    "the",
    "and",
    "for",
    "of",
    "in",
}


def extract_core_clues(text: str) -> set:
    if not text:
        return set()
    clean_text = re.sub(r"[^\w\s]", "", text.lower())
    return set(clean_text.split()) - STOP_WORDS


def classify_line_item(
    db: Session,
    row_text: str,
    requestor_name: str,
    *,
    wbs: str = "",
    purpose: str = "",
    instruction_to_vendor: str = "",
) -> dict:
    text_lower = (row_text or "").lower()
    req_clean = requestor_name.strip().lower() if requestor_name else ""
    labs = db.query(Lab).all()
    lab_groups = db.query(LabGroup).all()

    # W7-04 flow: WBS establishes Lab Group before lab-level clues are applied.
    matched_group = _match_lab_group_by_wbs(lab_groups, wbs)
    scoped_labs = _filter_labs_by_group(labs, matched_group)

    lab_match = _match_lab_by_text(scoped_labs, purpose)
    if lab_match:
        return _result(lab_match, matched_group, f"Purpose matched lab '{lab_match.lab_name}'")

    lab_match = _match_lab_by_text(scoped_labs, instruction_to_vendor)
    if lab_match:
        return _result(lab_match, matched_group, f"Vendor instruction matched lab '{lab_match.lab_name}'")

    if req_clean:
        lab_match = _match_lab_by_requestor(db, scoped_labs, req_clean)
        if lab_match:
            return _result(lab_match, matched_group, f"Requestor matched lab '{lab_match.lab_name}'")

    # Final fallback keeps the current demo behavior where configured lab codes
    # embedded anywhere in the row can still classify the line.
    lab_match = _match_lab_by_text(scoped_labs, text_lower)
    if lab_match:
        return _result(lab_match, matched_group, f"Row context matched lab '{lab_match.lab_name}'")

    if matched_group:
        return {
            "lab_id": None,
            "lab_group_id": matched_group.lab_group_id,
            "reason": f"WBS matched Lab Group '{matched_group.lab_group_name}', lab needs review.",
        }

    return {
        "lab_id": None,
        "lab_group_id": None,
        "reason": "Insufficient context clues. Manual review required.",
    }


def _match_lab_group_by_wbs(lab_groups: list, wbs: str):
    wbs_clean = (wbs or "").lower().strip()
    if not wbs_clean:
        return None
    for group in lab_groups:
        code = (getattr(group, "wbs_code", "") or "").lower().strip()
        if code and (code in wbs_clean or wbs_clean in code):
            return group
    return None


def _filter_labs_by_group(labs: list, group):
    if not group:
        return labs
    group_id = getattr(group, "lab_group_id", None)
    return [lab for lab in labs if getattr(lab, "lab_group_id", None) == group_id]


def _match_lab_by_text(labs: list, text: str):
    text_lower = (text or "").lower()
    if not text_lower:
        return None

    for lab in labs:
        code_clean = (getattr(lab, "lab_code", "") or "").lower().strip()
        if code_clean and code_clean in text_lower:
            return lab

    best_match_lab = None
    highest_clue_count = 0
    for lab in labs:
        clues = extract_core_clues(getattr(lab, "lab_name", "") or "")
        clues_found = sum(1 for clue in clues if clue in text_lower)
        if clues_found > highest_clue_count:
            highest_clue_count = clues_found
            best_match_lab = lab

    return best_match_lab


def _match_lab_by_requestor(db: Session, labs: list, requestor_name: str):
    lab_by_id = {getattr(lab, "lab_id", None): lab for lab in labs}
    for mapping in db.query(RequesterLabMapping).all():
        db_name = (getattr(mapping, "requester_name", "") or "").strip().lower()
        if db_name and (db_name in requestor_name or requestor_name in db_name):
            return lab_by_id.get(getattr(mapping, "default_lab_id", None))
    return None


def _result(lab, group, reason: str) -> dict:
    group_id = getattr(group, "lab_group_id", None) or getattr(lab, "lab_group_id", None)
    return {
        "lab_id": getattr(lab, "lab_id", None),
        "lab_group_id": group_id,
        "reason": reason,
    }
