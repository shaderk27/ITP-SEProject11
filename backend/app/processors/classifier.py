import re
from sqlalchemy.orm import Session
from app.models.config import Lab, LabGroup, RequesterLabMapping, SpendingCategory
from app.models.auth import User


def _is_smart_match(source_text: str, target_tag: str) -> bool:
    """
    STRICT word-boundary match. 
    Prevents 'test' from matching 'testing', or 'A' from matching 'apple'.
    """
    source_text = source_text.lower().strip()
    target_tag = target_tag.lower().strip()
    
    if not target_tag or not source_text:
        return False
        
    # Use regex word boundaries (\b) to ensure we only match exact, distinct words/phrases
    pattern = r'\b' + re.escape(target_tag) + r'\b'
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
    
    # --- REQUESTOR NORMALIZATION ---
    req_clean = ""
    if requestor_name:
        raw_name = requestor_name.split("@")[0]  # Drop the email domain if present
        req_clean = raw_name.replace(".", " ").replace("_", " ").strip().lower()
    # -------------------------------------------
    
    labs = db.query(Lab).all()
    lab_groups = db.query(LabGroup).all()
    categories = db.query(SpendingCategory).all()

    # 1. --- STRICT LAB & GROUP MATCHING ---
    matched_group = _match_lab_group_by_wbs(lab_groups, wbs)
    scoped_labs = _filter_labs_by_group(labs, matched_group)

    lab_match = None
    lab_reason = ""

    # Step 1: Check if lab name/venue specified in "purpose" field
    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, purpose_lower) or _match_lab_by_venue_tags(scoped_labs, purpose_lower)
        if lab_match:
            lab_reason = f"Purpose field matched lab '{lab_match.lab_name}'."

    # Step 2: Check if lab name/venue specified in "instructions to vendor" field
    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, vendor_lower) or _match_lab_by_venue_tags(scoped_labs, vendor_lower)
        if lab_match:
            lab_reason = f"Vendor instructions matched lab '{lab_match.lab_name}'."

    # Step 3: Check if "requester name" field = Lab IC name
    if not lab_match and req_clean:
        lab_match = _match_lab_by_requestor(db, scoped_labs, req_clean)
        if lab_match:
            lab_reason = f"Requestor matched Lab IC for '{lab_match.lab_name}'."

    # Step 4: WBS Explicit match (If group has only 1 lab, it's safe to assume)
    if not lab_match and matched_group:
        if len(scoped_labs) == 1:
            lab_match = scoped_labs[0]
            lab_reason = f"Inherited from explicit Lab Group WBS match '{matched_group.lab_group_name}'."
            
    # Step 5: Scan full row_text as absolute last resort (Safety net)
    if not lab_match:
        lab_match = _match_lab_by_text(scoped_labs, text_lower) or _match_lab_by_venue_tags(scoped_labs, text_lower)
        if lab_match:
            lab_reason = f"Row context explicitly mentioned lab '{lab_match.lab_name}'."

    # Step 4 (Fallbacks): Classify under "General" for Team Lead to sort
    if not lab_match and matched_group:
        lab_reason = f"WBS matched Lab Group '{matched_group.lab_group_name}', but specific lab was unclear."
        
    if not lab_match and not matched_group:
        lab_reason = "Insufficient lab context clues. Flagged for review."

    # 2. --- STRICT CATEGORY MATCHING ---
    category_match = None
    cat_reason = ""
    
    explicit_cat = (req_type or pr_category or "").strip()
    
    if explicit_cat:
        matched_categories = _find_matching_categories(categories, explicit_cat)
        
        if len(matched_categories) == 1:
            category_match = matched_categories[0]
            cat_reason = f"Matched category '{category_match.category_name}'."
        elif len(matched_categories) > 1:
            cat_names = ", ".join([c.category_name for c in matched_categories])
            cat_reason = f"Conflict detected (matched: {cat_names}). Flagged for manual review."
            category_match = None
        else:
            cat_reason = "Could not auto-determine category."
    else:
        cat_reason = "No category data provided."

    combined_reason = f"{lab_reason} {cat_reason}".strip()
    group_id = getattr(matched_group, "lab_group_id", None) or getattr(lab_match, "lab_group_id", None)

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
        if code and (wbs_clean == code or wbs_clean.startswith(f"{code}.") or wbs_clean.startswith(f"{code}-")):
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
        
    for lab in labs:
        venue_str = getattr(lab, "venue", "") or ""
        tags = [t.strip().lower() for t in venue_str.split(",") if t.strip()]
        
        for tag in tags:
            if tag and _is_smart_match(text_lower, tag):
                return lab
                
    return None

def _match_lab_by_text(labs: list, text: str):
    text_lower = (text or "").lower()
    if not text_lower:
        return None

    for lab in labs:
        # Strictly check lab code
        code_clean = (getattr(lab, "lab_code", "") or "").lower().strip()
        if code_clean and _is_smart_match(text_lower, code_clean):
            return lab
            
        # Strictly check lab name
        name_clean = (getattr(lab, "lab_name", "") or "").lower().strip()
        if name_clean and _is_smart_match(text_lower, name_clean):
            return lab

    return None

def _match_lab_by_requestor(db: Session, labs: list, requestor_name: str):
    """Matches normalized Excel requestor against the Lab IC's full name in the database."""
    lab_by_id = {getattr(lab, "lab_id", None): lab for lab in labs}
    
    # 1. Check against actual User table (Lab ICs currently assigned to a lab)
    lab_ics = db.query(User).filter(User.lab_id.isnot(None)).all()
    for ic in lab_ics:
        ic_name = (getattr(ic, "full_name", "") or "").strip().lower()
        if ic_name:
            ic_name_clean = ic_name.replace(".", " ").replace("_", " ")
            
            # Check for match (e.g., 'bobby joon' == 'bobby joon')
            if ic_name_clean == requestor_name or ic_name_clean in requestor_name or requestor_name in ic_name_clean:
                matched_lab = lab_by_id.get(ic.lab_id)
                if matched_lab:
                    return matched_lab

    # 2. Fallback to the explicit RequesterLabMapping table (Just in case!)
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

    matched_cats = []

    for cat in categories:
        name = (getattr(cat, "category_name", "") or "").lower().strip()
        if name == "general":
            continue
            
        is_match = False
        
        # 1. Check exact name using boundaries
        if name and _is_smart_match(text_lower, name):
            is_match = True
                
        # 2. Check tags if name didn't match
        if not is_match:
            desc = getattr(cat, "description", "") or ""
            if desc:
                tags = [t.strip().lower() for t in desc.split(",") if t.strip()]
                for tag in tags:
                    if tag and _is_smart_match(text_lower, tag):
                        is_match = True
                        break
        
        if is_match:
            matched_cats.append(cat)

    return matched_cats