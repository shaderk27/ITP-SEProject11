from sqlalchemy.orm import Session
from sqlalchemy import func
from app.models.config import Lab, RequesterLabMapping
import re

# Words we want the engine to ignore when guessing
STOP_WORDS = {"lab", "laboratory", "system", "systems", "room", "the", "and", "for", "of", "in"}

def extract_core_clues(text: str) -> set:
    """Takes a lab name, removes boring words, and returns the core 'clue' words."""
    if not text:
        return set()
    # Remove punctuation and split into words
    clean_text = re.sub(r'[^\w\s]', '', text.lower())
    words = set(clean_text.split())
    # Return only the meaningful words
    return words - STOP_WORDS

def classify_line_item(db: Session, row_text: str, requestor_name: str) -> dict:
    """
    ZERO-CONFIG ENGINE: Uses dynamic heuristics and clues to guess the lab 
    without needing a pre-defined rule dictionary.
    """
    text_lower = row_text.lower()
    req_clean = requestor_name.strip().lower() if requestor_name else ""

    # Fetch all labs so we can analyze them for clues
    labs = db.query(Lab).all()

    # ==========================================
    # CLUE 1: Direct Code / Location Match
    # ==========================================
    # If the CSV literally says "W3-05-12" or "E2L7", catch it instantly.
    for lab in labs:
        if lab.lab_code:
            code_clean = lab.lab_code.lower().strip()
            if code_clean and code_clean in text_lower:
                return {"lab_id": lab.lab_id, "reason": f"Auto-Detected Lab Code ({lab.lab_code})"}

    # ==========================================
    # CLUE 2: Semantic Name Matching (The Magic)
    # ==========================================
    # The engine dynamically breaks down the Lab Name into clues and searches for them.
    best_match_lab = None
    highest_clue_count = 0

    for lab in labs:
        if lab.lab_name:
            clues = extract_core_clues(lab.lab_name)
            
            # Count how many clues from the lab name appear in the CSV row
            clues_found = sum(1 for clue in clues if clue in text_lower)
            
            # If we found clues, and it's the strongest match so far, save it
            if clues_found > 0 and clues_found > highest_clue_count:
                highest_clue_count = clues_found
                best_match_lab = lab

    if best_match_lab:
        return {
            "lab_id": best_match_lab.lab_id, 
            "reason": f"Auto-Detected Context Clues matching '{best_match_lab.lab_name}'"
        }

    # ==========================================
    # CLUE 3: Historical Requestor Pattern
    # ==========================================
    if req_clean:
        mappings = db.query(RequesterLabMapping).all()
        for mapping in mappings:
            if mapping.requester_name:
                db_name = mapping.requester_name.strip().lower()
                if db_name in req_clean or req_clean in db_name:
                    return {"lab_id": mapping.default_lab_id, "reason": f"Auto-Assigned based on Requestor ({mapping.requester_name})"}

    # ==========================================
    # FALLBACK
    # ==========================================
    return {"lab_id": None, "reason": "Insufficient context clues. Manual review required."}