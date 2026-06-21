from sqlalchemy.orm import Session
from app.models.config import Lab, RequesterLabMapping
import re

STOP_WORDS = {"lab", "laboratory", "system", "systems", "room", "the", "and", "for", "of", "in"}

def extract_core_clues(text: str) -> set:
    if not text: return set()
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    return set(clean_text.split()) - STOP_WORDS

def classify_line_item(db: Session, row_text: str, requestor_name: str) -> dict:
    text_lower = row_text.lower()
    req_clean = requestor_name.strip().lower() if requestor_name else ""
    labs = db.query(Lab).all()

    # ==========================================
    # CLUE 1: Direct Code/Location Match (Using lab_code)
    # ==========================================
    for lab in labs:
        if lab.lab_code:
            code_clean = lab.lab_code.lower().strip()
            if code_clean and code_clean in text_lower:
                return {"lab_id": lab.lab_id, "reason": f"Auto-Detected Lab Code ({lab.lab_code})"}

    # ==========================================
    # CLUE 2: Semantic Name Match (Using lab_name)
    # ==========================================
    best_match_lab = None
    highest_clue_count = 0
    for lab in labs:
        if lab.lab_name:
            clues = extract_core_clues(lab.lab_name)
            clues_found = sum(1 for clue in clues if clue in text_lower)
            if clues_found > 0 and clues_found > highest_clue_count:
                highest_clue_count = clues_found
                best_match_lab = lab

    if best_match_lab:
        return {"lab_id": best_match_lab.lab_id, "reason": f"Auto-Detected Context Clues matching '{best_match_lab.lab_name}'"}

    # ==========================================
    # CLUE 3: Requestor Match
    # ==========================================
    if req_clean:
        mappings = db.query(RequesterLabMapping).all()
        for mapping in mappings:
            if mapping.requester_name:
                db_name = mapping.requester_name.strip().lower()
                if db_name in req_clean or req_clean in db_name:
                    return {"lab_id": mapping.default_lab_id, "reason": f"Auto-Assigned based on Requestor ({mapping.requester_name})"}

    return {"lab_id": None, "reason": "Insufficient context clues. Manual review required."}