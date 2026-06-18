# backend/app/tests/test_classifier.py
import pytest
from app.processors.classifier import classify_purchase_request

# We use a mock class to simulate Harry's PRLineItem
class MockPRLineItem:
    def __init__(self, wbs="", purpose="", instruction="", requestor=""):
        self.wbs = wbs
        self.purpose = purpose
        self.instruction_to_vendor = instruction
        self.requestor = requestor

@pytest.fixture
def mapping_data():
    return {
        "wbs_map": {"WBS-100": "Chemistry Group"},
        "keyword_map": {"analytical": "Analytical Lab", "microscope": "Bio Lab"},
        "requestor_map": {"Randy Kwok": "Software Lab"}
    }

def test_priority_1_purpose_match(mapping_data):
    item = MockPRLineItem(wbs="WBS-100", purpose="Buying analytical tools", requestor="Randy Kwok")
    group, lab = classify_purchase_request(
        item, mapping_data["wbs_map"], mapping_data["keyword_map"], mapping_data["requestor_map"]
    )
    assert group == "Chemistry Group"
    assert lab == "Analytical Lab" # Matches purpose, ignores requestor

def test_priority_3_requestor_match(mapping_data):
    item = MockPRLineItem(wbs="WBS-100", purpose="General items", requestor="Randy Kwok")
    group, lab = classify_purchase_request(
        item, mapping_data["wbs_map"], mapping_data["keyword_map"], mapping_data["requestor_map"]
    )
    assert group == "Chemistry Group"
    assert lab == "Software Lab" # Fallbacks to requestor since purpose/instruction have no keywords

def test_fallback_unassigned(mapping_data):
    item = MockPRLineItem(wbs="UNKNOWN", purpose="Random", instruction="None", requestor="Unknown Person")
    group, lab = classify_purchase_request(
        item, mapping_data["wbs_map"], mapping_data["keyword_map"], mapping_data["requestor_map"]
    )
    assert group == "Unassigned"
    assert lab == "Unassigned Lab"