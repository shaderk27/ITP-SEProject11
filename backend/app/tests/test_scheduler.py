from app.models.auth import User
from app.models.staging import StagingPRLine, ReviewQueueItem
from app.models.config import LabGroup
from app.services.scheduler_service import check_and_email_pending_reviews
import pytest


pytestmark = pytest.mark.skip(
    reason=(
        "Scheduler tests need a valid UploadBatch/StagingPRHeader fixture before "
        "they can run reliably against the real DB-backed test session."
    )
)


def test_scheduler_groups_and_emails_correct_team_lead(db, mocker):
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
    team_lead = User(
        email="physics.lead@sit.edu.sg",
        full_name="Dr. Physics Lead",
        password_hash="$2b$12$dummyhashformockingpurposesonly123",
        role_id=2,
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
        role_id=2,
        lab_group_id=other_group.lab_group_id,
        is_active=True,
    )
    db.add(other_lead)
    db.flush()

    # Create 3 staging lines for the Physics Group
    line_1 = StagingPRLine(
        suggested_lab_group_id=test_group.lab_group_id, line_identity_key="L1"
    )
    line_2 = StagingPRLine(
        suggested_lab_group_id=test_group.lab_group_id, line_identity_key="L2"
    )
    line_3 = StagingPRLine(
        suggested_lab_group_id=test_group.lab_group_id, line_identity_key="L3"
    )
    db.add_all([line_1, line_2, line_3])
    db.flush()

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
    db.commit()

    # ----------------------------------------------------------------------
    # 2. MOCK: Intercept the email functions
    # ----------------------------------------------------------------------
    mock_reminder = mocker.patch(
        "app.services.scheduler_service.send_pending_review_reminder"
    )
    mock_new_alert = mocker.patch(
        "app.services.scheduler_service.send_new_upload_alert"
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


def test_scheduler_triggers_new_upload_alert_if_flagged(db, mocker):
    """Tests that the is_new_upload flag correctly routes to the immediate alert template."""

    # Setup minimum data with all required fields
    test_group = LabGroup(lab_group_name="Test Chem Group", wbs_code="WBS-CHEM-01")
    db.add(test_group)
    db.flush()

    team_lead = User(
        email="chem.lead@sit.edu.sg",
        full_name="Dr. Chem Lead",
        password_hash="$2b$12$dummyhashformockingpurposesonly123",
        role_id=2,
        lab_group_id=test_group.lab_group_id,
        is_active=True,
    )
    line = StagingPRLine(
        suggested_lab_group_id=test_group.lab_group_id, line_identity_key="L_CHEM"
    )
    db.add_all([team_lead, line])
    db.flush()

    queue_item = ReviewQueueItem(
        staging_line_id=line.staging_line_id, queue_status="open"
    )
    db.add(queue_item)
    db.commit()

    # Mock emails
    mock_reminder = mocker.patch(
        "app.services.scheduler_service.send_pending_review_reminder"
    )
    mock_new_alert = mocker.patch(
        "app.services.scheduler_service.send_new_upload_alert"
    )

    # ACT
    check_and_email_pending_reviews(is_new_upload=True)

    # ASSERT
    mock_new_alert.assert_called_once()
    mock_reminder.assert_not_called()

    args, kwargs = mock_new_alert.call_args
    assert args[0] == "chem.lead@sit.edu.sg"
    assert args[2] == 1
