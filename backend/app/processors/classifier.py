# backend/app/processors/classifier.py
from app.models.upload import PRLineItem

def classify_purchase_request(
    item: PRLineItem, 
    wbs_to_group_map: dict[str, str], 
    keyword_to_lab_map: dict[str, str], 
    requestor_to_lab_map: dict[str, str]
) -> tuple[str, str]:
    """
    Classifies a PRLineItem into a Lab Group and Lab based on URS priority rules.
    Returns: (assigned_lab_group, assigned_lab)
    """
    # 1. Determine Lab Group using WBS
    assigned_group = wbs_to_group_map.get(item.wbs, "Unassigned")
    
    assigned_lab = "Unassigned Lab"
    
    # 2. Determine Lab - Priority 1: Purpose field
    if item.purpose:
        for keyword, lab_name in keyword_to_lab_map.items():
            if keyword.lower() in item.purpose.lower():
                assigned_lab = lab_name
                return assigned_group, assigned_lab

    # 3. Determine Lab - Priority 2: Instruction to Vendor
    if item.instruction_to_vendor:
        for keyword, lab_name in keyword_to_lab_map.items():
            if keyword.lower() in item.instruction_to_vendor.lower():
                assigned_lab = lab_name
                return assigned_group, assigned_lab

    # 4. Determine Lab - Priority 3: Requestor mapping
    if item.requestor:
        assigned_lab = requestor_to_lab_map.get(item.requestor, "Unassigned Lab")

    # Fallback to "Unassigned Lab" (General) if no matches found
    return assigned_group, assigned_lab