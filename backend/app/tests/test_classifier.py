from types import SimpleNamespace

from app.models.config import Lab, LabGroup, RequesterLabMapping
from app.processors.classifier import classify_line_item


class FakeQuery:
    def __init__(self, rows: list[SimpleNamespace]) -> None:
        self.rows = rows

    def all(self) -> list[SimpleNamespace]:
        return self.rows


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
                lab_id=10, lab_group_id=1, lab_code="CHEM-A", lab_name="Analytical Lab"
            ),
            SimpleNamespace(
                lab_id=20, lab_group_id=2, lab_code="BIO-M", lab_name="Microscope Lab"
            ),
            SimpleNamespace(
                lab_id=30, lab_group_id=1, lab_code="SW-L", lab_name="Software Lab"
            ),
        ]
        self.requester_mappings = [
            SimpleNamespace(requester_name="Randy Kwok", default_lab_id=30),
        ]

    def query(self, model):
        if model is LabGroup:
            return FakeQuery(self.lab_groups)
        if model is Lab:
            return FakeQuery(self.labs)
        if model is RequesterLabMapping:
            return FakeQuery(self.requester_mappings)
        return FakeQuery([])


def test_wbs_scopes_lab_group_and_purpose_selects_lab() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="buying analytical tools",
        requestor_name="Randy Kwok",
        wbs="WBS-100",
        purpose="Buying analytical tools",
    )

    assert result["lab_group_id"] == 1
    assert result["lab_id"] == 10
    assert "Purpose" in result["reason"]


def test_requestor_mapping_is_used_after_text_clues() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="general items",
        requestor_name="Randy Kwok",
        wbs="WBS-100",
        purpose="General items",
    )

    assert result["lab_group_id"] == 1
    assert result["lab_id"] == 30
    assert "Requestor" in result["reason"]


def test_instruction_to_vendor_selects_lab_after_purpose() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="delivery note says microscope room",
        requestor_name="Unknown Person",
        wbs="WBS-200",
        purpose="General lab purchase",
        instruction_to_vendor="Deliver to BIO-M bench",
    )

    assert result["lab_group_id"] == 2
    assert result["lab_id"] == 20
    assert "Vendor instruction" in result["reason"]


def test_unknown_row_is_left_for_review() -> None:
    result = classify_line_item(
        FakeDb(),
        row_text="random item",
        requestor_name="Unknown Person",
        wbs="UNKNOWN",
        purpose="Random",
    )

    assert result["lab_group_id"] is None
    assert result["lab_id"] is None
    assert "Manual review" in result["reason"]
