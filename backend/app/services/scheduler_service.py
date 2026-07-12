import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import func

from app.database import SessionLocal
from app.models.staging import ReviewQueueItem, StagingPRLine
from app.models.auth import User
from app.services.email_service import (
    send_pending_review_reminder,
    send_new_upload_alert,
)

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


def check_and_email_pending_reviews(is_new_upload: bool = False):
    """Queries the database for open review items and emails the respective Team Leads."""
    logger.info(
        f"[SCHEDULER] Running check for pending review items. (New Upload: {is_new_upload})"
    )

    with SessionLocal() as db:
        open_items = (
            db.query(
                StagingPRLine.suggested_lab_group_id,
                func.count(ReviewQueueItem.review_queue_id).label("pending_count"),
            )
            .join(
                ReviewQueueItem,
                ReviewQueueItem.staging_line_id == StagingPRLine.staging_line_id,
            )
            .filter(ReviewQueueItem.queue_status == "open")
            .filter(StagingPRLine.suggested_lab_group_id.isnot(None))
            .group_by(StagingPRLine.suggested_lab_group_id)
            .all()
        )

        for lab_group_id, pending_count in open_items:
            if pending_count > 0:
                team_leads = (
                    db.query(User)
                    .filter(
                        User.lab_group_id == lab_group_id,
                        User.role_id == 2,
                        User.is_active.is_(True),
                    )
                    .all()
                )

                for lead in team_leads:
                    if lead.email:
                        if is_new_upload:
                            send_new_upload_alert(
                                lead.email, lead.full_name or "Team Lead", pending_count
                            )
                        else:
                            send_pending_review_reminder(
                                lead.email, lead.full_name or "Team Lead", pending_count
                            )


def start_scheduler():
    """Attaches the jobs and starts the background timer if it isn't already running."""
    scheduler.add_job(
        check_and_email_pending_reviews,
        CronTrigger(day_of_week="mon", hour=9, minute=0, timezone="Asia/Singapore"),
        id="weekly_pending_review_reminder",
        replace_existing=True,
    )

    if not scheduler.running:
        scheduler.start()
        logger.info(
            "[SCHEDULER] Background scheduler started. Jobs queued for Asia/Singapore."
        )
    else:
        logger.info("[SCHEDULER] Scheduler is already running. Jobs updated.")


def shutdown_scheduler():
    """Gracefully kills the scheduler to prevent zombie processes."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("[SCHEDULER] Background scheduler shut down gracefully.")
