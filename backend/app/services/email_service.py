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
