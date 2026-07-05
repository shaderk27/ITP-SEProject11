import logging
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.models.config import Lab, Budget
from app.models.staging import PurchaseRequestLine 
from app.models.auth import User
from app.services.email_service import send_threshold_alert

logger = logging.getLogger(__name__)

def check_and_notify_lab_thresholds(db: Session, lab_id: int):
    lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
    if not lab:
        return

    # 1. Calculate Total Budget for this Lab
    total_budget = db.query(func.sum(Budget.budget_amount)).filter(Budget.lab_id == lab_id).scalar() or 0
    if total_budget <= 0:
        return

    # 2. Calculate Total Spent (Sum of committed PR lines for this lab)
    total_spent = db.query(func.sum(PurchaseRequestLine.amount_gst)).filter(
        PurchaseRequestLine.lab_id == lab_id
    ).scalar() or 0

    # 3. Calculate Utilization Percentage
    utilization_pct = (float(total_spent) / float(total_budget)) * 100

    # --- SMART FLAG RESET ---
    # If the budget is INCREASED later, we must reset the flags 
    # so they can receive warnings again in the future!
    if utilization_pct < 95 and lab.notified_95:
        lab.notified_95 = False
    if utilization_pct < 80 and lab.notified_80:
        lab.notified_80 = False
    if utilization_pct < 50 and lab.notified_50:
        lab.notified_50 = False
    # ------------------------

    # Determine which threshold we just crossed (check highest first)
    threshold_hit = None
    if utilization_pct >= 95 and not lab.notified_95:
        threshold_hit = 95
        lab.notified_95 = True
        lab.notified_80 = True # Catch-up in case of massive jump
        lab.notified_50 = True
    elif utilization_pct >= 80 and not lab.notified_80:
        threshold_hit = 80
        lab.notified_80 = True
        lab.notified_50 = True
    elif utilization_pct >= 50 and not lab.notified_50:
        threshold_hit = 50
        lab.notified_50 = True

    # Save the flags to the database IMMEDIATELY (even if we just reset them to False)
    db.commit() 

    if not threshold_hit:
        return # No NEW thresholds crossed, exit silently

    # 4. Gather Recipients (Lab IC & Team Lead)
    recipients = []
    
    # -- FETCH LAB IC (role_id == 3) --
    lab_ic = db.query(User).filter(User.lab_id == lab.lab_id, User.role_id == 3).first()
    if lab_ic and lab_ic.email:
        recipients.append(lab_ic.email)

    # -- FETCH TEAM LEAD (role_id == 2) --
    team_lead = db.query(User).filter(User.lab_group_id == lab.lab_group_id, User.role_id == 2).first()
    if team_lead and team_lead.email:
        recipients.append(team_lead.email)

    if not recipients:
        logger.warning(f"[THRESHOLD SERVICE] No Lab IC or Team Lead emails found for '{lab.lab_name}'.")
        return

    # 5. Craft the specific messaging
    spent_str = f"${float(total_spent):,.2f}"
    budget_str = f"${float(total_budget):,.2f}"
    
    if threshold_hit == 50:
        subject = f"Notice: {lab.lab_name} has reached 50% Budget Utilization"
        color = "#2563eb" # Blue
        message = "You have utilized half of your allocated lab budget. Please review upcoming planned expenses."
    elif threshold_hit == 80:
        subject = f"WARNING: {lab.lab_name} has reached 80% Budget Utilization"
        color = "#d97706" # Orange
        message = "Your lab is approaching its budget limit. Please prioritize essential purchases only."
    else: # 95%
        subject = f"CRITICAL: {lab.lab_name} has reached 95% Budget Utilization"
        color = "#dc2626" # Red
        message = "Immediate attention required. Your lab budget is nearly exhausted. Further PRs may be rejected unless additional funding is secured."

    # HTML Email Template
    html_body = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; border: 1px solid #e5e7eb; border-radius: 8px; overflow: hidden;">
        <div style="background-color: {color}; padding: 20px; text-align: center; color: white;">
            <h2 style="margin: 0;">Budget Threshold Alert</h2>
        </div>
        <div style="padding: 24px;">
            <p style="font-size: 16px; color: #374151;">Hello,</p>
            <p style="font-size: 16px; color: #374151;">
                This is an automated notification that <strong>{lab.lab_code} - {lab.lab_name}</strong> has crossed the 
                <strong style="color: {color};">{threshold_hit}%</strong> budget utilization threshold.
            </p>
            
            <div style="background-color: #f3f4f6; padding: 16px; border-radius: 6px; margin: 20px 0;">
                <p style="margin: 0 0 8px 0;"><strong>Total Allocated Budget:</strong> {budget_str}</p>
                <p style="margin: 0 0 8px 0;"><strong>Current Spending:</strong> {spent_str}</p>
                <p style="margin: 0;"><strong>Current Utilization:</strong> {utilization_pct:.1f}%</p>
            </div>

            <p style="font-size: 16px; color: {color}; font-weight: bold;">
                {message}
            </p>
            
            <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                Please log in to the SIT Lab Budget System to review your purchase lines.
            </p>
        </div>
    </div>
    """

    # 6. Fire the email
    send_threshold_alert(recipients, subject, html_body)