from types import SimpleNamespace

from app.models.config import Lab, LabGroup, RequesterLabMapping, SpendingCategory
from app.models.auth import User
from app.processors.classifier import classify_line_item


class FakeQuery:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    # Mock the SQLAlchemy .filter() method to just pass the rows through
    def filter(self, *args, **kwargs) -> "FakeQuery":
        return self

    def all(self) -> list[SimpleNamespace]:
        return self.rows

    def first(self) -> SimpleNamespace | None:
        return self.rows[0] if self.rows else None


class FakeDb:
    def __init__(self) -> None:
        self.lab_groups = [
            SimpleNamespace(lab_group_id=99, lab_group_name="Legacy", wbs_code="WBS"),
            SimpleNamespace(
                lab_group_id=1, lab_group_name="Chemistry Group", wbs_code="WBS-100"
            ),
            SimpleNamespace(
                lab_group_id=2, lab_group_name="Biology Group", wbs_code="WBS-200"
            ),
        ]
        self.labs = [
            SimpleNamespace(
                lab_id=10,
                lab_group_id=1,
                lab_code="CHEM-A",
                lab_name="Analytical Lab",
                venue="CHEM1, SR4A",
            ),
            SimpleNamespace(
                lab_id=20,
                lab_group_id=2,
                lab_code="BIO-M",
                lab_name="Microscope Lab",
                venue="BIO-L, W4L2",
            ),
            SimpleNamespace(
                lab_id=30,
                lab_group_id=1,
                lab_code="SW-L",
                lab_name="Software Lab",
                venue="",
            ),
        ]
        self.requester_mappings = [
            SimpleNamespace(requester_name="Randy Kwok", default_lab_id=30),
        ]
        self.categories = [
            SimpleNamespace(
                category_id=1,
                category_name="Equipment",
                description="hardware, computers, workstation",
            ),
            SimpleNamespace(
                category_id=2,
                category_name="Maintenance",
                description="repair, maintenance, servicing",
            ),
            SimpleNamespace(
                category_id=3,
                category_name="Consumables",
                description="chemicals, perishable",
            ),
            SimpleNamespace(
                category_id=4, category_name="General", description="fallback"
            ),
        ]
        # Mocked User table to support Lab IC matching
        self.users = [
            SimpleNamespace(
                user_id=1,
                full_name="Randy Kwok",
                email="randy@sit.edu",
                lab_id=30,
                lab_group_id=1,
            )
        ]

    def query(self, model):
        if model is LabGroup:
            return FakeQuery(self.lab_groups)
        if model is Lab:
            return FakeQuery(self.labs)
        if model is RequesterLabMapping:
            return FakeQuery(self.requester_mappings)
        if model is SpendingCategory:
            return FakeQuery(self.categories)
        if model is User:
            return FakeQuery(self.users)
        return FakeQuery([])


def test_purpose_matches_exact_lab_name() -> None:
    # Under strict matching, purpose must contain the exact name "Analytical Lab" or code "CHEM-A"
    result = classify_line_item(
        FakeDb(),
        row_text="buying lab tools",
        requestor_name="Unknown",
        wbs="WBS-100",
        purpose="Buying tools for Analytical Lab",
    )

    assert result["lab_group_id"] == 1
    assert result["lab_id"] == 10
    assert "Purpose field matched lab" in result["reason"]


def test_requestor_name_matches_lab_ic() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="general items",
        requestor_name="Randy.Kwok",
        wbs="WBS-100",
        purpose="General items",
    )

    assert result["lab_group_id"] == 1
    assert result["lab_id"] == 30
    assert "Requestor matched Lab IC" in result["reason"]


def test_vendor_instructions_match_lab_code() -> None:
    # "BIO-M" matches strictly at boundaries.
    result = classify_line_item(
        FakeDb(),
        row_text="delivery note",
        requestor_name="Unknown Person",
        wbs="WBS-200",
        purpose="General lab purchase",
        instruction_to_vendor="Deliver to BIO-M bench",
    )

    assert result["lab_group_id"] == 2
    assert result["lab_id"] == 20
    assert "Vendor instructions matched lab" in result["reason"]


# --- TESTS FOR VENUE TAGS & SMART CATEGORIES ---
def test_venue_tag_in_purpose_selects_lab() -> None:
    # "SR4A" is a venue tag for Analytical Lab. Since it's in the Purpose, it hits Client Priority 1.
    result = classify_line_item(
        FakeDb(),
        row_text="Delivery for testing",
        requestor_name="Unknown Person",
        wbs="WBS-100",
        purpose="General purchase for SR4A",
        instruction_to_vendor="Leave at door",
    )

    assert result["lab_group_id"] == 1
    assert result["lab_id"] == 10
    assert "Purpose field matched lab" in result["reason"]


def test_category_is_selected_by_exact_req_type() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="random item",
        requestor_name="Unknown",
        req_type="Equipment",
    )

    assert result["category_id"] == 1
    assert "Matched category" in result["reason"]


def test_category_conflict_sends_to_review() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="random item",
        requestor_name="Unknown",
        req_type="IT-Hardware (computers, accessories, maintenance)",
    )

    assert result["category_id"] is None
    assert "Conflict detected" in result["reason"]


def test_unknown_row_is_left_for_review() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="random mysterious object",
        requestor_name="Unknown Person",
        wbs="UNKNOWN",
        purpose="Random",
        req_type="Mysterious Object",
    )

    assert result["lab_group_id"] is None
    assert result["lab_id"] is None
    assert result["category_id"] is None
    assert "Insufficient lab context clues" in result["reason"]
    assert "Could not auto-determine category" in result["reason"]
