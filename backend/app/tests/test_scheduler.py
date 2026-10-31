from app.models.auth import User, Role
from app.models.staging import (
    UploadBatch,
    StagingPRHeader,
    StagingPRLine,
    ReviewQueueItem,
)
from app.models.config import LabGroup
from app.services.scheduler_service import check_and_email_pending_reviews


class _ExistingSessionContext:
    """Expose the transactional pytest session without closing it on exit."""

    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self.db

    def __exit__(self, exc_type, exc, traceback):
        return False


def _stage_review_lines(db, uploader, lab_group_id, prefix, count):
    batch = UploadBatch(
        uploaded_by=uploader.user_id,
        filename=f"{prefix}.xlsx",
        file_type="xlsx",
        upload_status="review_pending",
    )
    db.add(batch)
    db.flush()
    header = StagingPRHeader(
        batch_id=batch.batch_id,
        source_pr_number=f"PR-{prefix}",
    )
    db.add(header)
    db.flush()

    lines = []
    for index in range(1, count + 1):
        line = StagingPRLine(
            staging_header_id=header.staging_header_id,
            source_line_no=index,
            suggested_lab_group_id=lab_group_id,
            raw_line_json={"line_identity_key": f"{prefix}-{index}"},
        )
        db.add(line)
        db.flush()
        lines.append(line)
    return lines


def test_scheduler_groups_and_emails_correct_team_lead(db, admin_user, mocker):
    """
    Tests that the scheduler correctly groups open queue items by Lab Group,
    finds the correct Team Lead, counts the items accurately, and triggers the email.
    """
    # ----------------------------------------------------------------------
    # 1. ARRANGE: Set up the fake database state with ALL required fields
    # ----------------------------------------------------------------------

    # Create a dummy Lab Group (wbs_code added to satisfy DB constraints)
    test_group = LabGroup(lab_group_name="Test Physics Group", wbs_code="WBS-PHYS-01")
    db.add(test_group)
    db.flush()

    # Create a Team Lead (full_name and password_hash added)
    team_lead_role = db.query(Role).filter(Role.role_name == "teamlead").one()
    team_lead = User(
        email="physics.lead@sit.edu.sg",
        full_name="Dr. Physics Lead",
        password_hash="$2b$12$dummyhashformockingpurposesonly123",
        role_id=team_lead_role.role_id,
        lab_group_id=test_group.lab_group_id,
        is_active=True,
    )
    db.add(team_lead)

    # Create another user in a DIFFERENT group to prove they don't get emailed
    other_group = LabGroup(lab_group_name="Test Bio Group", wbs_code="WBS-BIO-01")
    db.add(other_group)
    db.flush()

    other_lead = User(
        email="bio.lead@sit.edu.sg",
        full_name="Dr. Bio Lead",
        password_hash="$2b$12$dummyhashformockingpurposesonly123",
        role_id=team_lead_role.role_id,
        lab_group_id=other_group.lab_group_id,
        is_active=True,
    )
    db.add(other_lead)
    db.flush()

    line_1, line_2, line_3 = _stage_review_lines(
        db, admin_user, test_group.lab_group_id, "SCHED-PHYS", 3
    )

    # Create Review Queue Items: 2 are OPEN, 1 is RESOLVED
    queue_1 = ReviewQueueItem(
        staging_line_id=line_1.staging_line_id, queue_status="open"
    )
    queue_2 = ReviewQueueItem(
        staging_line_id=line_2.staging_line_id, queue_status="open"
    )
    queue_3 = ReviewQueueItem(
        staging_line_id=line_3.staging_line_id, queue_status="resolved"
    )
    db.add_all([queue_1, queue_2, queue_3])
    db.flush()

    # ----------------------------------------------------------------------
    # 2. MOCK: Intercept the email functions
    # ----------------------------------------------------------------------
    mock_reminder = mocker.patch(
        "app.services.scheduler_service.send_pending_review_reminder"
    )
    mock_new_alert = mocker.patch(
        "app.services.scheduler_service.send_new_upload_alert"
    )
    mocker.patch(
        "app.services.scheduler_service.SessionLocal",
        return_value=_ExistingSessionContext(db),
    )

    # ----------------------------------------------------------------------
    # 3. ACT: Run the scheduler function manually
    # ----------------------------------------------------------------------
    check_and_email_pending_reviews(is_new_upload=False)

    # ----------------------------------------------------------------------
    # 4. ASSERT: Verify the math and targeting were perfect
    # ----------------------------------------------------------------------
    mock_reminder.assert_called_once()
    mock_new_alert.assert_not_called()

    args, kwargs = mock_reminder.call_args
    assert args[0] == "physics.lead@sit.edu.sg"
    assert args[2] == 2


def test_scheduler_triggers_new_upload_alert_if_flagged(db, admin_user, mocker):
    """Tests that the is_new_upload flag correctly routes to the immediate alert template."""

    # Setup minimum data with all required fields
    test_group = LabGroup(lab_group_name="Test Chem Group", wbs_code="WBS-CHEM-01")
    db.add(test_group)
    db.flush()

    team_lead_role = db.query(Role).filter(Role.role_name == "teamlead").one()
    team_lead = User(
        email="chem.lead@sit.edu.sg",
        full_name="Dr. Chem Lead",
        password_hash="$2b$12$dummyhashformockingpurposesonly123",
        role_id=team_lead_role.role_id,
        lab_group_id=test_group.lab_group_id,
        is_active=True,
    )
    db.add(team_lead)
    db.flush()
    line = _stage_review_lines(
        db, admin_user, test_group.lab_group_id, "SCHED-CHEM", 1
    )[0]

    queue_item = ReviewQueueItem(
        staging_line_id=line.staging_line_id, queue_status="open"
    )
    db.add(queue_item)
    db.flush()

    # Mock emails
    mock_reminder = mocker.patch(
        "app.services.scheduler_service.send_pending_review_reminder"
    )
    mock_new_alert = mocker.patch(
        "app.services.scheduler_service.send_new_upload_alert"
    )
    mocker.patch(
        "app.services.scheduler_service.SessionLocal",
        return_value=_ExistingSessionContext(db),
    )

    # ACT
    check_and_email_pending_reviews(is_new_upload=True)

    # ASSERT
    mock_new_alert.assert_called_once()
    mock_reminder.assert_not_called()

    args, kwargs = mock_new_alert.call_args
    assert args[0] == "chem.lead@sit.edu.sg"
    assert args[2] == 1
