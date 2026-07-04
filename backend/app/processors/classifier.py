import re
import difflib

from sqlalchemy.orm import Session
from app.models.config import Lab, LabGroup, RequesterLabMapping, SpendingCategory

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


def _is_smart_match(source_text: str, target_tag: str, threshold: float = 0.8) -> bool:
    """
    Intelligently checks if a tag exists in the source text.
    Handles weird punctuation (it-software) and minor typos (softwar vs software).
    """
    source_text = source_text.lower().strip()
    target_tag = target_tag.lower().strip()

    # 1. Fast Direct Match
    if target_tag in source_text or source_text in target_tag:
        return True

    # 2. Tokenized & Fuzzy Check
    words = [w for w in re.split(r"[^a-z0-9]", source_text) if len(w) > 2]

    for word in words:
        if word == target_tag:
            return True
        if difflib.SequenceMatcher(None, word, target_tag).ratio() >= threshold:
            return True

    return False


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
    req_type: str = "",
    pr_category: str = "",
) -> dict:
    text_lower = (row_text or "").lower()
    req_clean = requestor_name.strip().lower() if requestor_name else ""
    labs = db.query(Lab).all()
    lab_groups = db.query(LabGroup).all()
    categories = db.query(SpendingCategory).all()

    # 1. --- LAB & GROUP MATCHING (Uses Row Text vs Venue Tags) ---
    matched_group = _match_lab_group_by_wbs(lab_groups, wbs)
    scoped_labs = _filter_labs_by_group(labs, matched_group)

    lab_match = None
    lab_reason = ""

    lab_match = _match_lab_by_venue_tags(scoped_labs, text_lower)
    if lab_match:
        lab_reason = f"Row text matched lab venue tag for '{lab_match.lab_name}'."

    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, purpose)
        if lab_match:
            lab_reason = f"Purpose matched lab '{lab_match.lab_name}'."

    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, instruction_to_vendor)
        if lab_match:
            lab_reason = f"Vendor instruction matched lab '{lab_match.lab_name}'."

    if not lab_match and req_clean:
        lab_match = _match_lab_by_requestor(db, scoped_labs, req_clean)
        if lab_match:
            lab_reason = f"Requestor matched lab '{lab_match.lab_name}'."

    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, text_lower)
        if lab_match:
            lab_reason = f"Row context matched lab '{lab_match.lab_name}'."

    if not lab_match and matched_group:
        lab_reason = f"WBS matched Lab Group '{matched_group.lab_group_name}'."

    if not lab_match and not matched_group:
        lab_reason = "Insufficient lab context clues."

    # 2. --- CATEGORY MATCHING (Uses Req Type Only) ---
    category_match = None
    cat_reason = ""

    explicit_cat = (req_type or pr_category or "").strip()

    if explicit_cat:
        # Pass the Excel string into the Scorer to find the best match
        category_match = _match_category_by_text(categories, explicit_cat)
        if category_match:
            cat_reason = f"Excel column '{explicit_cat}' scored highest for category '{category_match.category_name}'."

    if not category_match:
        cat_reason = "Could not auto-determine category."

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
    exact_matches = []
    partial_matches = []
    for group in lab_groups:
        code = (getattr(group, "wbs_code", "") or "").lower().strip()
        if not code:
            continue
        if code == wbs_clean:
            exact_matches.append(group)
        elif code in wbs_clean or wbs_clean in code:
            partial_matches.append(group)
    if exact_matches:
        return max(exact_matches, key=lambda group: len(group.wbs_code or ""))
    if partial_matches:
        return max(partial_matches, key=lambda group: len(group.wbs_code or ""))
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
        tags = [t.strip().lower() for t in venue_str.split(",") if t.strip()]

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


# --- Position-Based Scoring Category Matcher ---
def _match_category_by_text(categories: list, text: str):
    text_lower = (text or "").lower()
    if not text_lower:
        return None

    best_match = None
    highest_score = 0

    # Helper function to dynamically score words based on WHERE they appear
    def score_word(word):
        word = word.strip().lower()
        if len(word) <= 2 or not _is_smart_match(text_lower, word):
            return 0

        # Find where the word is located in the text
        idx = text_lower.find(word)
        if idx == -1:
            return 15  # Fuzzy match fallback score

        # Calculate how early in the sentence it appears (0.0 = very beginning, 1.0 = very end)
        position_ratio = idx / max(len(text_lower), 1)

        if position_ratio <= 0.25:
            return 30  # Primary Subject (Start of sentence)
        elif position_ratio <= 0.60:
            return 20  # Secondary Context (Middle)
        else:
            return 10  # Modifier / Afterthought (End of sentence / parentheses)

    for cat in categories:
        name = (getattr(cat, "category_name", "") or "").lower().strip()
        if name == "general":
            continue

        current_cat_score = 0

        # 1. Score the exact Category Name
        if name:
            points = score_word(name)
            if points > 0:
                current_cat_score += (
                    points + 5
                )  # +5 Bonus for exactly matching the category title

        # 2. Score the Custom Description Tags
        desc = getattr(cat, "description", "") or ""
        if desc:
            tags = [t.strip().lower() for t in desc.split(",") if t.strip()]
            for tag in tags:
                points = score_word(tag)
                if points > 0:
                    current_cat_score += points

        # Declare the highest-scoring category the winner
        if current_cat_score > highest_score:
            highest_score = current_cat_score
            best_match = cat

    return best_match
