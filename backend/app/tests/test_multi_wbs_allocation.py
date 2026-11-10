"""
Automated tests for the Multi-WBS Transaction-Allocation Workflow (PR66).

Covers all acceptance criteria in multi-wbs-allocation-workflow-change_3.md
and all review requirements in pr66-multi-wbs-review.md:
  1. One PR header with several ordinary item rows creates one header and the correct number of staging lines.
  2. PR-level blank continuation cells inherit only the correct preceding PR information.
  3. WBS/allocation-only rows (both blank-Item-Details and repeated-Item-Details rows such as PR2500002163, PR2600001152, PR2600002702) are grouped onto the preceding purchase line without double-counting.
  4. Same-WBS quantity continuation rows collapse cleanly into the parent purchase line.
  5. Percentage allocations (e.g. $180 split 33.4% / 33.3% / 33.3% -> $60.12, $59.94, $59.94) calculate exact monetary portions with final-portion remainder absorption.
  6. Exact supplied multi-WBS allocations (e.g. PR2600002644: $50,000 + $31,000 = $81,000) are preserved and sent to Review Queue without equal splitting or creating a false extra purchase item.
  7. Existing upload identity format (`base_hash` and `base_hash::occurrence_N`) is preserved for duplicate compatibility.
  8. Team Lead budget authorization:
     - Team Lead can view/edit a multi-WBS line ONLY when every allocation belongs to that Team Lead's Lab Group.
     - Cross-Lab-Group multi-WBS lines require Admin review (403 for Team Lead).
     - Team Lead Lab Group / Lab selectors are scoped strictly to the Team Lead's Lab Group.
  9. Missing allocation amounts, non-reconciling allocation totals, and PR grand total mismatches are blocked until reconciled.
  10. Re-uploading the same allocation is treated as a duplicate; changing an allocation updates in place, records PRVersion/AuditLog history without duplicating spend, and reconciles across Dashboard, Alerts, Records, and Chatbot.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock
from uuid import uuid4

import pandas as pd
import pytest
from fastapi import BackgroundTasks, HTTPException

from app.api.alerts import get_alert_drilldown
from app.api.dashboard import get_breakdown, get_spending_summary
from app.api.records import list_committed_prs
from app.api.review import (
    AllocationCorrectionItem,
    CorrectionRequest,
    commit_batch,
    correct_queue_item,
    get_batch_detail,
    get_queue_item,
    list_batches,
)
from app.models.auth import Role, User
from app.models.config import Budget, BudgetPeriod, Lab, LabGroup, SpendingCategory
from app.models.staging import (
    PRVersion,
    PurchaseRequest,
    PurchaseRequestLine,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
)
from app.processors.upload_parser import (
    generate_line_identity_key,
    parse_line_items,
    read_upload_dataframe,
    validate_dataframe,
)
from app.repositories.upload_repository import UploadRepository
from app.schemas.chatbot_schema import ChatbotContextRequest
from app.services.chatbot_service import build_chatbot_context
from app.services.upload_service import UploadService


def _xlsx_bytes(rows: list[dict]) -> bytes:
    buf = BytesIO()
    pd.DataFrame(rows).to_excel(buf, index=False)
    return buf.getvalue()


def _base_row(
    *,
    pr: str = "",
    pr_status: str = "",
    pr_sub_date: str = "",
    requestor: str = "",
    purpose: str = "",
    grand_total: str | float | None = "",
    item_details: str = "",
    qty: str | float | None = "",
    uom: str = "LOT",
    unit_rate: str | float | None = "",
    delivery_date: str = "30-11-2026",
    mca: str = "",
    allocatn: str | float | None = "",
    wbs: str = "",
    req_type: str = "",
    instruction: str = "",
    curr: str = "SGD",
) -> dict:
    return {
        "PR": pr,
        "PO": "1000057748" if pr else "",
        "PR Status": pr_status,
        "PO Status": "OPEN" if pr else "",
        "Req Type": req_type,
        "PR Sub Date": pr_sub_date,
        "Requestor": requestor,
        "Purpose": purpose,
        "Curr": curr if pr else "",
        "Grand Total in SGD": grand_total,
        "Item Details": item_details,
        "Qty": qty,
        "UOM": uom if item_details else "",
        "Unit Rate": unit_rate,
        "Delivery Date": delivery_date if item_details else "",
        "MCA": mca,
        "Allocatn": allocatn,
        "WBS": wbs,
        "Instruction to Vendor": instruction,
    }


@pytest.fixture
def multi_wbs_seed(db):
    """Creates two Lab Groups (EQT and OOE), Labs, Categories, Team Leads, and FY budgets."""
    today = date.today()
    fy_year = today.year if today.month >= 4 else today.year - 1
    period = db.query(BudgetPeriod).filter(BudgetPeriod.year_no == fy_year).first()
    if period is None:
        period = BudgetPeriod(
            period_name=f"FY{fy_year}",
            year_no=fy_year,
            start_date=date(fy_year, 4, 1),
            end_date=date(fy_year + 1, 3, 31),
            is_closed=False,
        )
        db.add(period)
        db.flush()

    group_eqt = LabGroup(
        lab_group_name="BCA Equipment Group",
        wbs_code="R-BCAXX-R203-0004-EQT",
    )
    group_ooe = LabGroup(
        lab_group_name="BCA Operations Group",
        wbs_code="R-BCAXX-R203-0004-OOE",
    )
    db.add_all([group_eqt, group_ooe])
    db.flush()

    lab_eqt = Lab(
        lab_group_id=group_eqt.lab_group_id,
        lab_code="E6-05-03A",
        lab_name="Thermal Energy Storage Lab",
        venue="E6 05-03",
        is_general=False,
    )
    lab_eqt_2 = Lab(
        lab_group_id=group_eqt.lab_group_id,
        lab_code="E6-05-04A",
        lab_name="Chiller Testbed Lab",
        venue="E6 05-04",
        is_general=False,
    )
    lab_ooe = Lab(
        lab_group_id=group_ooe.lab_group_id,
        lab_code="E6-05-03B",
        lab_name="HVAC Commissioning Lab",
        venue="E6-05-03B",
        is_general=False,
    )
    db.add_all([lab_eqt, lab_eqt_2, lab_ooe])
    db.flush()

    cat_equip = SpendingCategory(
        category_name="TES Equipment",
        description="chilled-water, equipment",
    )
    cat_services = SpendingCategory(
        category_name="TES Services",
        description="consumables, general services, commissioning",
    )
    db.add_all([cat_equip, cat_services])
    db.flush()

    now = datetime.now(UTC)
    db.add_all(
        [
            Budget(
                period_id=period.period_id,
                lab_group_id=group_eqt.lab_group_id,
                lab_id=None,
                category_id=None,
                budget_amount=Decimal("100000.00"),
                created_at=now,
                updated_at=now,
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group_eqt.lab_group_id,
                lab_id=lab_eqt.lab_id,
                category_id=cat_equip.category_id,
                budget_amount=Decimal("80000.00"),
                created_at=now,
                updated_at=now,
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group_ooe.lab_group_id,
                lab_id=None,
                category_id=None,
                budget_amount=Decimal("100000.00"),
                created_at=now,
                updated_at=now,
            ),
            Budget(
                period_id=period.period_id,
                lab_group_id=group_ooe.lab_group_id,
                lab_id=lab_ooe.lab_id,
                category_id=cat_services.category_id,
                budget_amount=Decimal("60000.00"),
                created_at=now,
                updated_at=now,
            ),
        ]
    )
    db.flush()

    tl_role = db.query(Role).filter(Role.role_name == "teamlead").first()
    role_id = tl_role.role_id if tl_role else 2
    teamlead_eqt = User(
        user_id=99001,
        role_id=role_id,
        role=tl_role or MagicMock(role_name="teamlead"),
        full_name="EQT Team Lead",
        email=f"tl.eqt.{uuid4().hex[:6]}@sit.edu.sg",
        password_hash="placeholder",
        lab_group_id=group_eqt.lab_group_id,
        is_active=True,
    )
    teamlead_ooe = User(
        user_id=99002,
        role_id=role_id,
        role=tl_role or MagicMock(role_name="teamlead"),
        full_name="OOE Team Lead",
        email=f"tl.ooe.{uuid4().hex[:6]}@sit.edu.sg",
        password_hash="placeholder",
        lab_group_id=group_ooe.lab_group_id,
        is_active=True,
    )

    return {
        "period": period,
        "group_eqt": group_eqt,
        "group_ooe": group_ooe,
        "lab_eqt": lab_eqt,
        "lab_eqt_2": lab_eqt_2,
        "lab_ooe": lab_ooe,
        "cat_equip": cat_equip,
        "cat_services": cat_services,
        "teamlead_eqt": teamlead_eqt,
        "teamlead_ooe": teamlead_ooe,
        "req_date_str": (period.start_date or date(2026, 9, 8)).strftime("%d-%m-%Y"),
        "req_date": period.start_date or date(2026, 9, 8),
    }


def test_parser_handles_continuation_items_same_wbs_qty_and_multi_wbs_allocations():
    """
    Verifies:
      - Ordinary item continuation rows inherit preceding PR header fields.
      - Same-WBS MCA=Quantity continuation rows collapse into the parent item.
      - Genuine multi-WBS continuation rows (PR2600002644: $50,000 + $31,000 = $81,000)
        stay attached to the preceding item without creating a false extra item.
    """
    rows = [
        _base_row(
            pr="PR2600002636",
            pr_status="Approved (SVP)",
            pr_sub_date="07-09-2026",
            requestor="mingze.chai",
            purpose="Electronic Balance Adaptor",
            grand_total="210.00",
            item_details="Transport Delivery",
            qty="1.000",
            unit_rate="30.00",
            mca="NA",
            wbs="A-TI3-P502-CI01-OOE",
        ),
        _base_row(
            item_details="A&D AC Adaptor - 12V1A",
            qty="2.000",
            unit_rate="90.00",
            mca="Quantity",
            allocatn="1.000",
            wbs="A-TI3-P502-CI01-OOE",
        ),
        _base_row(
            allocatn="1.000",
            wbs="A-TI3-P502-CI01-OOE",
        ),
        _base_row(
            pr="PR2600002644",
            pr_status="Approved (Procurement)",
            pr_sub_date="08-09-2026",
            requestor="qiong.chen",
            purpose="Supply, installation and commissioning of a 3 m3 chilled-water TES system",
            grand_total="88,000.00",
            item_details="Supply installation and commissioning of a 3 m chilled-water TES system",
            qty="1.000",
            unit_rate="81,000.00",
            mca="Amount",
            allocatn="50000.00",
            wbs="R-BCAXX-R203-0004-EQT",
        ),
        _base_row(
            allocatn="31000.00",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
        _base_row(
            item_details="Testing and commissioning of the complete TES system",
            qty="1.000",
            unit_rate="5,000.00",
            mca="NA",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
        _base_row(
            item_details="Dismantling of the complete TES installation",
            qty="1.000",
            unit_rate="2,000.00",
            mca="NA",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
    ]

    df = pd.DataFrame(rows)
    errors = validate_dataframe(df)
    assert errors == []

    items = parse_line_items(df)
    assert len(items) == 5

    pr1_items = [it for it in items if it.pr_number == "PR2600002636"]
    assert len(pr1_items) == 2
    assert pr1_items[1].amount_gst == Decimal("180.00")
    assert pr1_items[1].wbs_allocations == ()

    pr2_items = [it for it in items if it.pr_number == "PR2600002644"]
    assert len(pr2_items) == 3
    assert sum(it.amount_gst for it in pr2_items) == Decimal("88000.00")
    assert all(it.requestor == "qiong.chen" for it in pr2_items)
    assert all(it.pr_sub_date == "2026-09-08" for it in pr2_items)

    tes_item = pr2_items[0]
    assert tes_item.amount_gst == Decimal("81000.00")
    assert len(tes_item.wbs_allocations) == 2
    assert tes_item.wbs_allocations[0]["wbs"] == "R-BCAXX-R203-0004-EQT"
    assert tes_item.wbs_allocations[0]["amount_gst"] == "50000.00"
    assert tes_item.wbs_allocations[1]["wbs"] == "R-BCAXX-R203-0004-OOE"
    assert tes_item.wbs_allocations[1]["amount_gst"] == "31000.00"


def test_repeated_item_allocation_rows_and_percentage_splits_not_double_counted():
    """
    Verifies PR66 review requirements #1, #2, and #4:
      - Repeated item rows with allocation values (PR2500002163 $77,520, PR2600001152 $176,
        PR2600002702 $180) are grouped as portions of one source item and not counted twice.
      - Percentage allocations (33.4%, 33.3%, 33.3% on a $180 item) compute $60.12, $59.94,
        and $59.94, with the final portion absorbing rounding remainder.
      - Genuine repeated non-allocation items use `base_hash::occurrence_N` identity format.
    """
    rows = [
        # Case A: PR2500002163 ($77,520 item repeated across 2 same-WBS allocation rows)
        _base_row(
            pr="PR2500002163",
            pr_status="Approved (Procurement)",
            pr_sub_date="05-09-2026",
            requestor="user.alpha",
            purpose="High-capacity test system",
            grand_total="77,520.00",
            item_details="High-Capacity System Unit",
            qty="2.000",
            uom="EA",
            unit_rate="38,760.00",
            mca="Quantity",
            allocatn="1.000",
            wbs="A-SAME-WBS-01",
        ),
        _base_row(
            item_details="High-Capacity System Unit",
            qty="2.000",
            uom="EA",
            unit_rate="38,760.00",
            mca="Quantity",
            allocatn="1.000",
            wbs="A-SAME-WBS-01",
        ),
        # Case B: PR2600002702 ($180 freight item repeated across 3 WBS rows with 33.4%, 33.3%, 33.3%)
        _base_row(
            pr="PR2600002702",
            pr_status="Approved (SVP)",
            pr_sub_date="06-09-2026",
            requestor="user.beta",
            purpose="Shared freight charges",
            grand_total="180.00",
            item_details="Freight & Handling Charge",
            qty="1.000",
            uom="LOT",
            unit_rate="180.00",
            mca="Percentage",
            allocatn="33.4",
            wbs="R-WBS-PCT-01",
        ),
        _base_row(
            item_details="Freight & Handling Charge",
            qty="1.000",
            uom="LOT",
            unit_rate="180.00",
            mca="Percentage",
            allocatn="33.3",
            wbs="R-WBS-PCT-02",
        ),
        _base_row(
            item_details="Freight & Handling Charge",
            qty="1.000",
            uom="LOT",
            unit_rate="180.00",
            mca="Percentage",
            allocatn="33.3",
            wbs="R-WBS-PCT-03",
        ),
        # Case C: Genuine repeated non-allocation items (no Allocatn value) preserve `::occurrence_2`
        _base_row(
            pr="PR2600009999",
            pr_status="Approved (SVP)",
            pr_sub_date="07-09-2026",
            requestor="user.gamma",
            purpose="Identical cables",
            grand_total="200.00",
            item_details="Standard Patch Cable",
            qty="1.000",
            uom="EA",
            unit_rate="100.00",
            mca="NA",
            allocatn="",
            wbs="A-CABLE-WBS",
        ),
        _base_row(
            item_details="Standard Patch Cable",
            qty="1.000",
            uom="EA",
            unit_rate="100.00",
            mca="NA",
            allocatn="",
            wbs="A-CABLE-WBS",
        ),
    ]

    df = read_upload_dataframe("test_repeated.xlsx", _xlsx_bytes(rows))
    assert validate_dataframe(df) == []

    items = parse_line_items(df)
    assert len(items) == 4

    item_2163 = next(it for it in items if it.pr_number == "PR2500002163")
    assert item_2163.amount_gst == Decimal("77520.00")
    assert item_2163.wbs_allocations == ()

    item_2702 = next(it for it in items if it.pr_number == "PR2600002702")
    assert item_2702.amount_gst == Decimal("180.00")
    assert len(item_2702.wbs_allocations) == 3
    assert [a["amount_gst"] for a in item_2702.wbs_allocations] == [
        "60.12",
        "59.94",
        "59.94",
    ]
    assert sum(Decimal(a["amount_gst"]) for a in item_2702.wbs_allocations) == Decimal(
        "180.00"
    )

    cable_items = [it for it in items if it.pr_number == "PR2600009999"]
    assert len(cable_items) == 2
    expected_base = generate_line_identity_key(
        pr_number="PR2600009999",
        item_details="Standard Patch Cable",
        wbs="A-CABLE-WBS",
        requestor="user.gamma",
        purpose="Identical cables",
    )
    assert cable_items[0].line_identity_key == expected_base
    assert cable_items[1].line_identity_key == f"{expected_base}::occurrence_2"


def test_teamlead_budget_scope_and_admin_only_cross_group_multi_wbs(
    db, admin_user, tmp_path, multi_wbs_seed
):
    """
    Verifies PR66 review requirement #3 (Team Lead Budget Scope):
      - A multi-WBS line spanning two different Lab Groups (EQT and OOE) is hidden from
        both Team Leads' batch lists and batch details, and returns 403 Forbidden if a
        Team Lead tries to view or resolve it. Only Admin can review and resolve it.
      - A multi-WBS line where ALL allocations belong to the EQT Lab Group IS visible
        and editable by the EQT Team Lead (with Lab Group / Lab options restricted to EQT),
        and returns 403 Forbidden if the EQT Team Lead attempts to assign any portion to OOE.
    """
    seed = multi_wbs_seed
    tl_eqt = seed["teamlead_eqt"]
    tl_ooe = seed["teamlead_ooe"]

    # 1. Upload a cross-Lab-Group multi-WBS PR (EQT + OOE)
    cross_rows = [
        _base_row(
            pr="PR-CROSS-GROUP",
            pr_status="Approved (Procurement)",
            pr_sub_date=seed["req_date_str"],
            requestor="qiong.chen",
            purpose="Cross-group TES system",
            grand_total="81,000.00",
            item_details="Cross-group TES installation",
            qty="1.000",
            unit_rate="81,000.00",
            mca="Amount",
            allocatn="50000.00",
            wbs="R-BCAXX-R203-0004-EQT",
            req_type="TES Equipment",
        ),
        _base_row(
            allocatn="31000.00",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
    ]
    service_cross = UploadService(
        UploadRepository(tmp_path / f"cross-{uuid4().hex}.json"), db=db
    )
    cross_res = service_cross.process_upload(
        filename="cross_group.xlsx",
        content=_xlsx_bytes(cross_rows),
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
        current_user=admin_user,
    )
    cross_batch_id = cross_res["persistence"]["db_batch_id"]
    admin_detail = get_batch_detail(cross_batch_id, db=db, current_user=admin_user)
    cross_q_id = admin_detail.prs[0].lines[0].review_queue_id

    # Neither Team Lead can see the cross-group line in batch detail or open it
    tl_eqt_detail = get_batch_detail(cross_batch_id, db=db, current_user=tl_eqt)
    assert tl_eqt_detail.prs == []

    with pytest.raises(HTTPException) as tl_view_exc:
        get_queue_item(cross_q_id, db=db, current_user=tl_eqt)
    assert tl_view_exc.value.status_code == 403

    with pytest.raises(HTTPException) as tl_edit_exc:
        correct_queue_item(
            cross_q_id,
            CorrectionRequest(
                allocations=[
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-EQT",
                        amount_gst=Decimal("50000.00"),
                        lab_group_id=seed["group_eqt"].lab_group_id,
                        lab_id=seed["lab_eqt"].lab_id,
                        category_id=seed["cat_equip"].category_id,
                    ),
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-OOE",
                        amount_gst=Decimal("31000.00"),
                        lab_group_id=seed["group_ooe"].lab_group_id,
                        lab_id=seed["lab_ooe"].lab_id,
                        category_id=seed["cat_services"].category_id,
                    ),
                ]
            ),
            db=db,
            current_user=tl_eqt,
        )
    assert tl_edit_exc.value.status_code == 403

    # 2. Upload an intra-Lab-Group multi-WBS PR where both WBS codes belong to EQT
    same_group_rows = [
        _base_row(
            pr="PR-SAME-GROUP-EQT",
            pr_status="Approved (SVP)",
            pr_sub_date=seed["req_date_str"],
            requestor="qiong.chen",
            purpose="Intra-group EQT split",
            grand_total="10,000.00",
            item_details="Dual EQT sub-account purchase",
            qty="1.000",
            unit_rate="10,000.00",
            mca="Amount",
            allocatn="6000.00",
            wbs="R-BCAXX-R203-0004-EQT-A",
            req_type="TES Equipment",
        ),
        _base_row(
            allocatn="4000.00",
            wbs="R-BCAXX-R203-0004-EQT-B",
        ),
    ]
    service_same = UploadService(
        UploadRepository(tmp_path / f"same-{uuid4().hex}.json"), db=db
    )
    same_res = service_same.process_upload(
        filename="same_group.xlsx",
        content=_xlsx_bytes(same_group_rows),
        uploader_email=tl_eqt.email,
        uploader_name=tl_eqt.full_name,
        uploader_role="teamlead",
        current_user=tl_eqt,
    )
    same_batch_id = same_res["persistence"]["db_batch_id"]

    # EQT Team Lead sees this batch and its queue item; OOE Team Lead does not
    eqt_batches = list_batches(db=db, current_user=tl_eqt)
    assert any(b.batch_id == same_batch_id for b in eqt_batches)
    ooe_batches = list_batches(db=db, current_user=tl_ooe)
    assert all(b.batch_id != same_batch_id for b in ooe_batches)

    eqt_detail = get_batch_detail(same_batch_id, db=db, current_user=tl_eqt)
    same_q_id = eqt_detail.prs[0].lines[0].review_queue_id
    q_item_tl = get_queue_item(same_q_id, db=db, current_user=tl_eqt)

    # Dropdown options returned to EQT Team Lead only contain EQT Lab Group and EQT Labs
    assert [g.lab_group_id for g in q_item_tl.available_lab_groups] == [
        seed["group_eqt"].lab_group_id
    ]
    assert all(
        lab.lab_group_id == seed["group_eqt"].lab_group_id
        for lab in q_item_tl.available_labs
    )

    # EQT Team Lead cannot save an allocation pointing to OOE Lab Group (403 Forbidden)
    with pytest.raises(HTTPException) as cross_assign_exc:
        correct_queue_item(
            same_q_id,
            CorrectionRequest(
                allocations=[
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-EQT-A",
                        amount_gst=Decimal("6000.00"),
                        lab_group_id=seed["group_eqt"].lab_group_id,
                        lab_id=seed["lab_eqt"].lab_id,
                        category_id=seed["cat_equip"].category_id,
                    ),
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-EQT-B",
                        amount_gst=Decimal("4000.00"),
                        lab_group_id=seed["group_ooe"].lab_group_id,
                        lab_id=seed["lab_ooe"].lab_id,
                        category_id=seed["cat_services"].category_id,
                    ),
                ]
            ),
            db=db,
            current_user=tl_eqt,
        )
    assert cross_assign_exc.value.status_code == 403

    # EQT Team Lead CAN confirm allocations across labs within their own EQT Lab Group
    correct_res = correct_queue_item(
        same_q_id,
        CorrectionRequest(
            comment="Confirmed within EQT group",
            allocations=[
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-EQT-A",
                    amount_gst=Decimal("6000.00"),
                    lab_group_id=seed["group_eqt"].lab_group_id,
                    lab_id=seed["lab_eqt"].lab_id,
                    category_id=seed["cat_equip"].category_id,
                ),
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-EQT-B",
                    amount_gst=Decimal("4000.00"),
                    lab_group_id=seed["group_eqt"].lab_group_id,
                    lab_id=seed["lab_eqt_2"].lab_id,
                    category_id=seed["cat_equip"].category_id,
                ),
            ],
        ),
        db=db,
        current_user=tl_eqt,
    )
    assert correct_res.success is True
    assert correct_res.new_queue_status == "resolved"


def test_exact_multi_wbs_workflow_review_commit_reupload_and_downstream_reconciliation(
    db, admin_user, tmp_path, multi_wbs_seed
):
    seed = multi_wbs_seed
    store_path = tmp_path / f"store-{uuid4().hex}.json"
    service = UploadService(UploadRepository(store_path), db=db)

    rows = [
        _base_row(
            pr="PR2600002644",
            pr_status="Approved (Procurement)",
            pr_sub_date=seed["req_date_str"],
            requestor="qiong.chen",
            purpose="Chilled-water TES system for E6 05-03",
            grand_total="88,000.00",
            item_details="Supply installation and commissioning of a 3 m chilled-water TES system",
            qty="1.000",
            unit_rate="81,000.00",
            mca="Amount",
            allocatn="50000.00",
            wbs="R-BCAXX-R203-0004-EQT",
            req_type="TES Equipment",
        ),
        _base_row(
            allocatn="31000.00",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
        _base_row(
            item_details="Testing and commissioning of the complete TES system",
            qty="1.000",
            unit_rate="5,000.00",
            mca="NA",
            wbs="R-BCAXX-R203-0004-OOE",
            req_type="TES Services",
            instruction="E6-05-03B",
        ),
        _base_row(
            item_details="Dismantling of the complete TES installation",
            qty="1.000",
            unit_rate="2,000.00",
            mca="NA",
            wbs="R-BCAXX-R203-0004-OOE",
            req_type="TES Services",
            instruction="E6-05-03B",
        ),
    ]

    # 1. Upload: creates 1 staging header, 3 staging lines, and routes multi-WBS line to Review Queue
    upload_res = service.process_upload(
        filename="DivPRReport_2644.xlsx",
        content=_xlsx_bytes(rows),
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
        current_user=admin_user,
    )
    assert upload_res["success"] is True
    assert upload_res["counts"]["total_lines"] == 3
    assert upload_res["persistence"]["headers_inserted"] == 1
    assert upload_res["persistence"]["lines_inserted"] == 3
    assert upload_res["counts"]["needs_review"] >= 1

    batch_id = upload_res["persistence"]["db_batch_id"]
    batch_detail = get_batch_detail(batch_id, db=db, current_user=admin_user)
    assert len(batch_detail.prs) == 1
    multi_q_line = next(
        line for line in batch_detail.prs[0].lines if len(line.wbs_allocations) == 2
    )
    assert Decimal(multi_q_line.amount_gst) == Decimal("81000.00")
    assert multi_q_line.allocations_reconciled is True
    assert Decimal(multi_q_line.allocated_total_gst or "0") == Decimal("81000.00")

    # 2. Inspect QueueItemDetail in Review Queue
    q_detail = get_queue_item(
        multi_q_line.review_queue_id, db=db, current_user=admin_user
    )
    assert len(q_detail.wbs_allocations) == 2
    assert q_detail.wbs_allocations[0].wbs_code == "R-BCAXX-R203-0004-EQT"
    assert Decimal(q_detail.wbs_allocations[0].amount_gst or "0") == Decimal("50000.00")
    assert q_detail.wbs_allocations[1].wbs_code == "R-BCAXX-R203-0004-OOE"
    assert Decimal(q_detail.wbs_allocations[1].amount_gst or "0") == Decimal("31000.00")

    # 3. Attempting to save non-reconciling allocation portions ($50,000 + $20,000 != $81,000) is rejected
    with pytest.raises(HTTPException) as bad_save_exc:
        correct_queue_item(
            multi_q_line.review_queue_id,
            CorrectionRequest(
                comment="Invalid sum",
                allocations=[
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-EQT",
                        amount_gst=Decimal("50000.00"),
                        lab_group_id=seed["group_eqt"].lab_group_id,
                        lab_id=seed["lab_eqt"].lab_id,
                        category_id=seed["cat_equip"].category_id,
                    ),
                    AllocationCorrectionItem(
                        wbs_code="R-BCAXX-R203-0004-OOE",
                        amount_gst=Decimal("20000.00"),
                        lab_group_id=seed["group_ooe"].lab_group_id,
                        lab_id=seed["lab_ooe"].lab_id,
                        category_id=seed["cat_services"].category_id,
                    ),
                ],
            ),
            db=db,
            current_user=admin_user,
        )
    assert bad_save_exc.value.status_code == 400
    assert "does not reconcile" in bad_save_exc.value.detail

    # 4. Confirm exact allocations ($50,000 to EQT Lab + $31,000 to OOE Lab = $81,000)
    correct_queue_item(
        multi_q_line.review_queue_id,
        CorrectionRequest(
            comment="Confirmed exact multi-WBS split",
            allocations=[
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-EQT",
                    amount_gst=Decimal("50000.00"),
                    lab_group_id=seed["group_eqt"].lab_group_id,
                    lab_id=seed["lab_eqt"].lab_id,
                    category_id=seed["cat_equip"].category_id,
                ),
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-OOE",
                    amount_gst=Decimal("31000.00"),
                    lab_group_id=seed["group_ooe"].lab_group_id,
                    lab_id=seed["lab_ooe"].lab_id,
                    category_id=seed["cat_services"].category_id,
                ),
            ],
        ),
        db=db,
        current_user=admin_user,
    )

    for other_q in (
        db.query(ReviewQueueItem)
        .join(StagingPRLine)
        .join(StagingPRHeader)
        .filter(StagingPRHeader.batch_id == batch_id)
        .filter(ReviewQueueItem.queue_status == "open")
        .all()
    ):
        correct_queue_item(
            other_q.review_queue_id,
            CorrectionRequest(
                lab_group_id=seed["group_ooe"].lab_group_id,
                lab_id=seed["lab_ooe"].lab_id,
                category_id=seed["cat_services"].category_id,
            ),
            db=db,
            current_user=admin_user,
        )

    # 5. Commit the batch and verify exact portions are stored (not equal split!)
    commit_res = commit_batch(
        batch_id, BackgroundTasks(), db=db, current_user=admin_user
    )
    assert commit_res.success is True
    assert commit_res.prs_created == 1
    assert commit_res.lines_created == 4

    pr = (
        db.query(PurchaseRequest)
        .filter(PurchaseRequest.source_pr_number == "PR2600002644")
        .one()
    )
    committed_lines = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.pr_id == pr.pr_id)
        .order_by(PurchaseRequestLine.pr_line_id)
        .all()
    )
    assert len(committed_lines) == 4
    assert sum(Decimal(str(cl.amount_gst)) for cl in committed_lines) == Decimal(
        "88000.00"
    )

    eqt_spend = sum(
        Decimal(str(cl.amount_gst))
        for cl in committed_lines
        if cl.lab_id == seed["lab_eqt"].lab_id
    )
    ooe_spend = sum(
        Decimal(str(cl.amount_gst))
        for cl in committed_lines
        if cl.lab_id == seed["lab_ooe"].lab_id
    )
    assert eqt_spend == Decimal("50000.00")
    assert ooe_spend == Decimal("38000.00")

    # 6. Verify Dashboard, Alerts Drilldown, PR Records, and Chatbot reconcile
    dash_summary = get_spending_summary(
        date_range="all",
        start_date=seed["req_date"],
        end_date=seed["req_date"],
        db=db,
        current_user=admin_user,
    )
    assert Decimal(
        dash_summary.by_lab_group.get(str(seed["group_eqt"].lab_group_id), "0")
    ) == Decimal("50000.00")
    assert Decimal(
        dash_summary.by_lab_group.get(str(seed["group_ooe"].lab_group_id), "0")
    ) == Decimal("38000.00")

    dash_breakdown = get_breakdown(
        date_range="all",
        start_date=seed["req_date"],
        end_date=seed["req_date"],
        period_id=seed["period"].period_id,
        db=db,
        current_user=admin_user,
    )
    bd_by_group = {g.lab_group_id: g for g in dash_breakdown.lab_groups}
    assert Decimal(
        bd_by_group[seed["group_eqt"].lab_group_id].actual_spend_sgd
    ) == Decimal("50000.00")
    assert Decimal(
        bd_by_group[seed["group_ooe"].lab_group_id].actual_spend_sgd
    ) == Decimal("38000.00")

    alert_dd = get_alert_drilldown(
        period_id=seed["period"].period_id,
        start_date=seed["req_date"],
        end_date=seed["req_date"],
        db=db,
        current_user=admin_user,
    )
    dd_by_group = {g.lab_group_id: g for g in alert_dd.lab_groups}
    assert Decimal(
        dd_by_group[seed["group_eqt"].lab_group_id].actual_spend_sgd
    ) == Decimal("50000.00")
    assert Decimal(
        dd_by_group[seed["group_ooe"].lab_group_id].actual_spend_sgd
    ) == Decimal("38000.00")

    records_list = list_committed_prs(
        date_range="all",
        start_date=seed["req_date"],
        end_date=seed["req_date"],
        db=db,
        current_user=admin_user,
    )
    rec_pr = next(r for r in records_list if r.source_pr_number == "PR2600002644")
    assert Decimal(rec_pr.grand_total_sgd) == Decimal("88000.00")
    assert sum(Decimal(rl.amount_gst) for rl in rec_pr.lines) == Decimal("88000.00")

    chat_ctx = build_chatbot_context(
        db,
        admin_user,
        ChatbotContextRequest(
            query_type="budget_utilisation_summary",
            period_id=seed["period"].period_id,
            start_date=seed["req_date"],
            end_date=seed["req_date"],
        ),
    )
    chat_by_lab = {b.lab_id: b for b in chat_ctx.budget_context}
    assert Decimal(chat_by_lab[seed["lab_eqt"].lab_id].approved_spend_sgd) == Decimal(
        "50000.00"
    )
    assert Decimal(chat_by_lab[seed["lab_ooe"].lab_id].approved_spend_sgd) == Decimal(
        "38000.00"
    )

    # 7. Re-uploading the identical file is treated as a duplicate
    dup_res = service.process_upload(
        filename="DivPRReport_2644_dup.xlsx",
        content=_xlsx_bytes(rows),
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
        current_user=admin_user,
    )
    assert dup_res["counts"]["duplicate_skipped"] == 3
    assert dup_res["counts"]["accepted"] == 0
    assert dup_res["counts"]["reupload_updated"] == 0

    # 8. Changing the allocation ($45,000 + $36,000 = $81,000) updates in place without duplicating spend
    changed_rows = list(rows)
    changed_rows[0] = dict(rows[0], Allocatn="45000.00")
    changed_rows[1] = dict(rows[1], Allocatn="36000.00")

    upd_res = service.process_upload(
        filename="DivPRReport_2644_updated.xlsx",
        content=_xlsx_bytes(changed_rows),
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
        current_user=admin_user,
    )
    assert upd_res["counts"]["reupload_updated"] == 1
    assert upd_res["counts"]["duplicate_skipped"] == 2

    upd_batch_id = upd_res["persistence"]["db_batch_id"]
    upd_detail = get_batch_detail(upd_batch_id, db=db, current_user=admin_user)
    upd_q_line = upd_detail.prs[0].lines[0]
    correct_queue_item(
        upd_q_line.review_queue_id,
        CorrectionRequest(
            comment="Confirmed updated 45k/36k split",
            allocations=[
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-EQT",
                    amount_gst=Decimal("45000.00"),
                    lab_group_id=seed["group_eqt"].lab_group_id,
                    lab_id=seed["lab_eqt"].lab_id,
                    category_id=seed["cat_equip"].category_id,
                ),
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-OOE",
                    amount_gst=Decimal("36000.00"),
                    lab_group_id=seed["group_ooe"].lab_group_id,
                    lab_id=seed["lab_ooe"].lab_id,
                    category_id=seed["cat_services"].category_id,
                ),
            ],
        ),
        db=db,
        current_user=admin_user,
    )
    commit_batch(upd_batch_id, BackgroundTasks(), db=db, current_user=admin_user)

    db.expire_all()
    updated_lines = (
        db.query(PurchaseRequestLine)
        .filter(PurchaseRequestLine.pr_id == pr.pr_id)
        .all()
    )
    assert len(updated_lines) == 4
    assert sum(Decimal(str(ul.amount_gst)) for ul in updated_lines) == Decimal(
        "88000.00"
    )
    assert sum(
        Decimal(str(ul.amount_gst))
        for ul in updated_lines
        if ul.lab_id == seed["lab_eqt"].lab_id
    ) == Decimal("45000.00")
    assert sum(
        Decimal(str(ul.amount_gst))
        for ul in updated_lines
        if ul.lab_id == seed["lab_ooe"].lab_id
    ) == Decimal("43000.00")

    versions = (
        db.query(PRVersion)
        .filter(PRVersion.pr_id == pr.pr_id)
        .order_by(PRVersion.version_id)
        .all()
    )
    assert len(versions) == 2
    assert versions[1].change_type == "updated"
    assert "allocation_updates" in versions[1].new_data


def test_missing_allocation_amounts_and_grand_total_mismatch_guards(
    db, admin_user, tmp_path, multi_wbs_seed
):
    seed = multi_wbs_seed
    store_path = tmp_path / f"store-missing-{uuid4().hex}.json"
    service = UploadService(UploadRepository(store_path), db=db)

    rows = [
        _base_row(
            pr="PR-MISSING-ALLOC",
            pr_status="Pending",
            pr_sub_date=seed["req_date_str"],
            requestor="qiong.chen",
            purpose="Chilled-water TES system",
            grand_total="95,000.00",
            item_details="Supply installation of TES system",
            qty="1.000",
            unit_rate="81,000.00",
            mca="Amount",
            allocatn="50000.00",
            wbs="R-BCAXX-R203-0004-EQT",
            req_type="TES Equipment",
        ),
        _base_row(
            allocatn="",
            wbs="R-BCAXX-R203-0004-OOE",
        ),
    ]

    res = service.process_upload(
        filename="missing_alloc.xlsx",
        content=_xlsx_bytes(rows),
        uploader_email=admin_user.email,
        uploader_name=admin_user.full_name,
        uploader_role="admin",
        current_user=admin_user,
    )
    batch_id = res["persistence"]["db_batch_id"]
    detail = get_batch_detail(batch_id, db=db, current_user=admin_user)
    q_line = detail.prs[0].lines[0]
    assert q_line.allocations_reconciled is False
    assert "missing" in q_line.review_reason.lower()

    with pytest.raises(HTTPException) as missing_exc:
        correct_queue_item(
            q_line.review_queue_id,
            CorrectionRequest(
                lab_group_id=seed["group_eqt"].lab_group_id,
                lab_id=seed["lab_eqt"].lab_id,
                category_id=seed["cat_equip"].category_id,
            ),
            db=db,
            current_user=admin_user,
        )
    assert missing_exc.value.status_code == 400
    assert "missing allocation amounts" in missing_exc.value.detail

    correct_queue_item(
        q_line.review_queue_id,
        CorrectionRequest(
            allocations=[
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-EQT",
                    amount_gst=Decimal("50000.00"),
                    lab_group_id=seed["group_eqt"].lab_group_id,
                    lab_id=seed["lab_eqt"].lab_id,
                    category_id=seed["cat_equip"].category_id,
                ),
                AllocationCorrectionItem(
                    wbs_code="R-BCAXX-R203-0004-OOE",
                    amount_gst=Decimal("31000.00"),
                    lab_group_id=seed["group_ooe"].lab_group_id,
                    lab_id=seed["lab_ooe"].lab_id,
                    category_id=seed["cat_services"].category_id,
                ),
            ],
        ),
        db=db,
        current_user=admin_user,
    )

    with pytest.raises(HTTPException) as grand_tot_exc:
        commit_batch(batch_id, BackgroundTasks(), db=db, current_user=admin_user)
    assert grand_tot_exc.value.status_code == 409
    assert "do not reconcile with PR grand total" in grand_tot_exc.value.detail
