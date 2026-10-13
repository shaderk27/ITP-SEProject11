import re

from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.config import Lab, LabGroup, RequesterLabMapping, SpendingCategory


def _is_smart_match(source_text: str, target_tag: str) -> bool:
    source_text = (source_text or "").lower().strip()
    target_tag = (target_tag or "").lower().strip()
    if not target_tag or not source_text:
        return False

    pattern = r"\b" + re.escape(target_tag) + r"\b"
    return bool(re.search(pattern, source_text))


def classify_line_item(
    db: Session,
    row_text: str,
    requestor_name: str,
    *,
    wbs: str = "",
    purpose: str = "",
    instruction_to_vendor: str = "",
    req_type: str = "",
    pr_category: str = "",
) -> dict:
    text_lower = (row_text or "").lower()
    purpose_lower = (purpose or "").lower()
    vendor_lower = (instruction_to_vendor or "").lower()

    req_clean = ""
    if requestor_name:
        raw_name = requestor_name.split("@")[0]
        req_clean = raw_name.replace(".", " ").replace("_", " ").strip().lower()

    labs = db.query(Lab).all()
    lab_groups = db.query(LabGroup).all()
    categories = db.query(SpendingCategory).all()

    matched_group = _match_lab_group_by_wbs(lab_groups, wbs)
    scoped_labs = _filter_labs_by_group(labs, matched_group)

    lab_match = None
    lab_reason = ""

    if not lab_match:
        lab_match = _match_lab_by_text(
            scoped_labs, purpose_lower
        ) or _match_lab_by_venue_tags(scoped_labs, purpose_lower)
        if lab_match:
            lab_reason = f"Purpose field matched lab '{lab_match.lab_name}'."

    if not lab_match:
        lab_match = _match_lab_by_text(
            scoped_labs, vendor_lower
        ) or _match_lab_by_venue_tags(scoped_labs, vendor_lower)
        if lab_match:
            lab_reason = f"Vendor instructions matched lab '{lab_match.lab_name}'."

    if not lab_match and req_clean:
        lab_match = _match_lab_by_requestor(db, scoped_labs, req_clean)
        if lab_match:
            lab_reason = f"Requestor matched Lab IC for '{lab_match.lab_name}'."

    if not lab_match and matched_group and len(scoped_labs) == 1:
        lab_match = scoped_labs[0]
        lab_reason = f"Inherited from explicit Lab Group WBS match '{matched_group.lab_group_name}'."

    if not lab_match:
        lab_match = _match_lab_by_text(
            scoped_labs, text_lower
        ) or _match_lab_by_venue_tags(scoped_labs, text_lower)
        if lab_match:
            lab_reason = f"Row context explicitly mentioned lab '{lab_match.lab_name}'."

    if not lab_match and matched_group:
        lab_reason = f"WBS matched Lab Group '{matched_group.lab_group_name}', but specific lab was unclear."

    if not lab_match and not matched_group:
        lab_reason = "Insufficient lab context clues. Flagged for review."

    category_match = None
    cat_reason = ""
    explicit_cat = (req_type or pr_category or "").strip()

    if explicit_cat:
        matched_categories = _find_matching_categories(categories, explicit_cat)
        if len(matched_categories) == 1:
            category_match = matched_categories[0]
            cat_reason = f"Matched category '{category_match.category_name}'."
        elif len(matched_categories) > 1:
            cat_names = ", ".join(
                [category.category_name for category in matched_categories]
            )
            cat_reason = (
                f"Conflict detected (matched: {cat_names}). Flagged for manual review."
            )
        else:
            cat_reason = "Could not auto-determine category."
    else:
        cat_reason = "No category data provided."

    combined_reason = f"{lab_reason} {cat_reason}".strip()
    group_id = getattr(matched_group, "lab_group_id", None) or getattr(
        lab_match, "lab_group_id", None
    )

    return {
        "lab_id": getattr(lab_match, "lab_id", None),
        "lab_group_id": group_id,
        "category_id": getattr(category_match, "category_id", None),
        "reason": combined_reason,
    }


def _match_lab_group_by_wbs(lab_groups: list, wbs: str):
    wbs_clean = (wbs or "").lower().strip()
    if not wbs_clean:
        return None

    for group in sorted(lab_groups, key=lambda g: len(g.wbs_code or ""), reverse=True):
        code = (getattr(group, "wbs_code", "") or "").lower().strip()
        if code and (
            wbs_clean == code
            or wbs_clean.startswith(f"{code}.")
            or wbs_clean.startswith(f"{code}-")
        ):
            return group

    return None


def _filter_labs_by_group(labs: list, group):
    if not group:
        return labs
    group_id = getattr(group, "lab_group_id", None)
    return [lab for lab in labs if getattr(lab, "lab_group_id", None) == group_id]


def _match_lab_by_venue_tags(labs: list, text_lower: str):
    if not text_lower:
        return None

    best_match = None
    highest_match_len = 0
    for lab in labs:
        venue_str = getattr(lab, "venue", "") or ""
        tags = [tag.strip().lower() for tag in venue_str.split(",") if tag.strip()]
        for tag in tags:
            if len(tag) > 2 and _is_smart_match(text_lower, tag):
                if len(tag) > highest_match_len:
                    highest_match_len = len(tag)
                    best_match = lab

    return best_match


def _match_lab_by_text(labs: list, text: str):
    text_lower = (text or "").lower()
    if not text_lower:
        return None

    for lab in labs:
        code_clean = (getattr(lab, "lab_code", "") or "").lower().strip()
        if code_clean and _is_smart_match(text_lower, code_clean):
            return lab

        name_clean = (getattr(lab, "lab_name", "") or "").lower().strip()
        if name_clean and _is_smart_match(text_lower, name_clean):
            return lab

    return None


def _match_lab_by_requestor(db: Session, labs: list, requestor_name: str):
    lab_by_id = {getattr(lab, "lab_id", None): lab for lab in labs}

    lab_ics = db.query(User).filter(User.lab_assignments.any()).all()
    for ic in lab_ics:
        ic_name = (getattr(ic, "full_name", "") or "").strip().lower()
        if ic_name:
            ic_name_clean = ic_name.replace(".", " ").replace("_", " ")
            if (
                ic_name_clean == requestor_name
                or ic_name_clean in requestor_name
                or requestor_name in ic_name_clean
            ):
                # A Lab IC can run several labs: take the first one inside the
                # PR's lab group, primary lab first.
                for assignment in sorted(
                    ic.lab_assignments, key=lambda a: not a.is_primary
                ):
                    matched_lab = lab_by_id.get(assignment.lab_id)
                    if matched_lab:
                        return matched_lab

    for mapping in db.query(RequesterLabMapping).all():
        db_name = (getattr(mapping, "requester_name", "") or "").strip().lower()
        if db_name:
            db_name_clean = db_name.replace(".", " ").replace("_", " ")
            if db_name_clean in requestor_name or requestor_name in db_name_clean:
                matched_lab = lab_by_id.get(getattr(mapping, "default_lab_id", None))
                if matched_lab:
                    return matched_lab

    return None


def _find_matching_categories(categories: list, text: str) -> list:
    text_lower = (text or "").lower()
    if not text_lower:
        return []

    matched_categories = []
    for category in categories:
        name = (getattr(category, "category_name", "") or "").lower().strip()
        if name == "general":
            continue

        is_match = bool(name and _is_smart_match(text_lower, name))

        if not is_match:
            description = getattr(category, "description", "") or ""
            tags = [
                tag.strip().lower() for tag in description.split(",") if tag.strip()
            ]
            is_match = any(_is_smart_match(text_lower, tag) for tag in tags)

        if is_match:
            matched_categories.append(category)

    return matched_categories
