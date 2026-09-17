"""
Shared pytest fixtures for the backend test suite.

The `db` fixture wraps every test in a SAVEPOINT so DB writes performed by
the test (including `db.commit()` inside the code-under-test) never persist
to the budget_system database. Each test starts clean, no truncation needed.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Callable, Generator

import pytest
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.database import engine
from app.models.auth import User
from app.models.config import Lab, LabGroup, SpendingCategory, BudgetPeriod, Budget
from app.models.staging import (
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
    UploadBatch,
)


@pytest.fixture
def db() -> Generator[Session, None, None]:
    """
    Per-test transactional session against the real budget_system DB.

    Pattern: open a connection, start an outer transaction, bind a session to
    it, then open a SAVEPOINT. Code-under-test's `db.commit()` only commits
    the savepoint, not the outer transaction. At teardown we rollback the
    outer transaction so nothing the test wrote persists.
    """
    connection = engine.connect()
    transaction = connection.begin()
    TestSession = sessionmaker(bind=connection, autoflush=False, autocommit=False)
    session = TestSession()
    session.begin_nested()

    @event.listens_for(session, "after_transaction_end")
    def _restart_savepoint(sess: Session, trans):
        # When the inner SAVEPOINT ends, open a new one so subsequent
        # code-under-test commits keep landing inside the outer transaction.
        if trans.nested and not trans._parent.nested:
            sess.begin_nested()

    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()


@pytest.fixture
def admin_user(db: Session) -> User:
    user = db.query(User).filter(User.email == "admin@test.com").first()
    if user is None:
        pytest.skip(
            "Seed admin@test.com missing. Run backend/seeds/dev_seed.sql first."
        )
    return user


@pytest.fixture
def seed_refs(db: Session) -> dict:
    """A real lab_group / lab / category trio from seed data."""
    group = db.query(LabGroup).filter(LabGroup.lab_group_name != "General").first()
    if group is None:
        group = db.query(LabGroup).first()
    lab = db.query(Lab).filter(Lab.lab_group_id == group.lab_group_id).first()
    if lab is None:
        pytest.skip("No labs seeded for any lab_group; run dev_seed.sql.")
    category = db.query(SpendingCategory).first()
    period = db.query(BudgetPeriod).first()

    # --- TOP-DOWN ENVELOPE SAFETY GUARD ---
    # Automatically injects a massive envelope budget for this group if it doesn't 
    # exist, ensuring that legacy integration tests building labs dynamically 
    # don't crash from the new 400 Bad Request mathematical threshold guards.
    if period and group:
        existing_env = db.query(Budget).filter(
            Budget.lab_group_id == group.lab_group_id, 
            Budget.lab_id.is_(None)
        ).first()
        if not existing_env:
            db.add(Budget(
                period_id=period.period_id, 
                lab_group_id=group.lab_group_id, 
                budget_amount=Decimal("9999999.00")
            ))
            db.flush()
    # ----------------------------------------

    return {
        "lab_group_id": group.lab_group_id,
        "lab_id": lab.lab_id,
        "category_id": category.category_id,
    }


@pytest.fixture
def make_staging_batch(db: Session, admin_user, seed_refs) -> Callable:
    """
    Factory: build a UploadBatch + 1 StagingPRHeader + N StagingPRLine rows.

    Defaults to ready_to_commit so tests can immediately call commit_batch.
    Set needs_review=True to also create an open ReviewQueueItem on line 1
    (so the batch ends up in review_pending status).
    """

    def _make(
        source_pr_number: str = "PR-TEST-001",
        grand_total: Decimal = Decimal("100.00"),
        lines: list[tuple[str, Decimal]] | None = None,
        needs_review: bool = False,
    ) -> UploadBatch:
        if lines is None:
            lines = [("default item", grand_total)]

        batch = UploadBatch(
            uploaded_by=admin_user.user_id,
            filename=f"test_{source_pr_number}.xlsx",
            file_type="xlsx",
            upload_status="review_pending" if needs_review else "ready_to_commit",
        )
        db.add(batch)
        db.flush()

        header = StagingPRHeader(
            batch_id=batch.batch_id,
            source_pr_number=source_pr_number,
            requestor_name="Test Requestor",
            purpose="Test purpose",
            wbs_code="WBS-TEST-001",
            grand_total_sgd=grand_total,
        )
        db.add(header)
        db.flush()

        for i, (desc, amount) in enumerate(lines, start=1):
            line_identity_key = f"{source_pr_number}::{desc}"
            line = StagingPRLine(
                staging_header_id=header.staging_header_id,
                source_line_no=i,
                item_details=desc,
                qty=Decimal("1"),
                unit_rate=amount,
                amount_gst=amount,
                suggested_lab_group_id=seed_refs["lab_group_id"],
                suggested_lab_id=seed_refs["lab_id"],
                suggested_category_id=seed_refs["category_id"],
                classification_status="confident",
                review_status="not_required",
                raw_line_json={
                    "line_identity_key": line_identity_key,
                    "item_details": desc,
                    "pr_status": "",
                    "po_number": "",
                    "po_status": "",
                },
            )
            db.add(line)
            db.flush()

            if needs_review and i == 1:
                db.add(
                    ReviewQueueItem(
                        staging_line_id=line.staging_line_id,
                        queue_status="open",
                        priority="normal",
                        review_reason="Test review item.",
                    )
                )

        db.flush()
        return batch

    return _make