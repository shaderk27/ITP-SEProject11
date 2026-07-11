import smtplib
import os
import logging
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Set up standard production logging (silent unless there's an error)
logger = logging.getLogger(__name__)

load_dotenv()

SMTP_USER = os.environ.get("SMTP_USER")
SMTP_PASS = os.environ.get("SMTP_PASS")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))


def send_threshold_alert(to_emails: list[str], subject: str, html_content: str):
    """Sends an HTML email via Gmail SMTP using credentials from .env."""

    # Fail silently if there is no one to email or missing credentials
    if not to_emails or not SMTP_USER or not SMTP_PASS:
        return

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)

        for email_addr in to_emails:
            msg = MIMEMultipart()
            msg["From"] = f"SIT Lab Budget System <{SMTP_USER}>"
            msg["To"] = email_addr
            msg["Subject"] = subject
            msg.attach(MIMEText(html_content, "html"))

            server.sendmail(SMTP_USER, email_addr, msg.as_string())

        server.quit()

    except Exception as e:
        # Logs the error to the server silently instead of printing it to the terminal
        logger.error(f"[EMAIL SERVICE] Failed to send email: {e}")


def send_pending_review_reminder(
    to_email: str, team_lead_name: str, pending_count: int
):
    """Sends a reminder to Team Leads about pending PR corrections."""
    if not to_email or not SMTP_USER or not SMTP_PASS:
        return

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)

        subject = f"Action Required: {pending_count} PR Lines Pending Review"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #f59e0b; padding: 20px; text-align: center; color: white;">
                <h2 style="margin: 0;">Pending Review Queue Reminder</h2>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; color: #374151;">Hello {team_lead_name},</p>
                <p style="font-size: 16px; color: #374151;">
                    This is an automated reminder that you currently have <strong>{pending_count} item(s)</strong> 
                    in your review queue waiting for classification corrections.
                </p>
                <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                    Please log in to the SIT Lab Budget System and navigate to the <strong>Review Queue</strong> to resolve these items so the batch can be committed.
                </p>
            </div>
        </div>
        """

        msg = MIMEMultipart()
        msg["From"] = f"SIT Lab Budget System <{SMTP_USER}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()

    except Exception as e:
        logger.error(f"[EMAIL SERVICE] Failed to send reminder email: {e}")


def send_new_upload_alert(to_email: str, team_lead_name: str, pending_count: int):
    """Sends an immediate alert when a new upload creates review queue items."""
    if not to_email or not SMTP_USER or not SMTP_PASS:
        return

    try:
        server = smtplib.SMTP(SMTP_HOST, SMTP_PORT)
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)

        subject = f"New PR Upload: {pending_count} Items Require Review"

        html_body = f"""
        <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
            <div style="background-color: #2563eb; padding: 20px; text-align: center; color: white;">
                <h2 style="margin: 0;">New Purchase Requests Uploaded</h2>
            </div>
            <div style="padding: 24px;">
                <p style="font-size: 16px; color: #374151;">Hello {team_lead_name},</p>
                <p style="font-size: 16px; color: #374151;">
                    An Admin has just processed a new batch of Purchase Requests. 
                    You currently have <strong>{pending_count} item(s)</strong> in your queue waiting for classification corrections.
                </p>
                <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                    Please log in to the SIT Lab Budget System and navigate to the <strong>Review Queue</strong> to resolve these items.
                </p>
            </div>
        </div>
        """

        msg = MIMEMultipart()
        msg["From"] = f"SIT Lab Budget System <{SMTP_USER}>"
        msg["To"] = to_email
        msg["Subject"] = subject
        msg.attach(MIMEText(html_body, "html"))

        server.sendmail(SMTP_USER, to_email, msg.as_string())
        server.quit()

    except Exception as e:
        logger.error(f"[EMAIL SERVICE] Failed to send new upload alert: {e}")
