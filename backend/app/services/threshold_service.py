import logging
from datetime import date
from sqlalchemy import func, or_, and_
from app.database import SessionLocal
from app.models.config import Lab, Budget, BudgetPeriod
from app.models.staging import PurchaseRequestLine, PurchaseRequest
from app.models.auth import User
from app.services.email_service import send_threshold_alert

logger = logging.getLogger(__name__)

def check_and_notify_lab_thresholds(lab_id: int):
    with SessionLocal() as db:
        lab = db.query(Lab).filter(Lab.lab_id == lab_id).first()
        if not lab:
            return

        # 1. Determine the CURRENT Fiscal Year based on today's date
        today = date.today()
        current_period = db.query(BudgetPeriod).filter(
            BudgetPeriod.start_date <= today,
            BudgetPeriod.end_date >= today
        ).first()

        if not current_period:
            return

        # 2. FY-Aware Budget Math
        total_budget = db.query(func.sum(Budget.budget_amount)).filter(
            Budget.lab_id == lab_id,
            Budget.period_id == current_period.period_id
        ).scalar() or 0

        if total_budget <= 0:
            return

        # 3. FY-Aware & Status-Aware Spent Math
        total_spent = db.query(func.sum(PurchaseRequestLine.amount_gst)).join(
            PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id
        ).filter(
            PurchaseRequestLine.lab_id == lab_id,
            PurchaseRequest.request_date >= current_period.start_date,
            PurchaseRequest.request_date <= current_period.end_date,
            or_(
                PurchaseRequestLine.pr_status.is_(None),
                and_(
                    PurchaseRequestLine.pr_status.not_ilike("%reject%"),
                    PurchaseRequestLine.pr_status.not_ilike("%cancel%")
                )
            )
        ).scalar() or 0

        utilization_pct = (float(total_spent) / float(total_budget)) * 100

        # --- SMART FY RESET ---
        if lab.alert_period_id != current_period.period_id:
            lab.notified_50 = False
            lab.notified_80 = False
            lab.notified_95 = False
            lab.alert_period_id = current_period.period_id

        # Secondary Reset: if an admin manually increases the budget later
        if utilization_pct < 95 and lab.notified_95:
            lab.notified_95 = False
        if utilization_pct < 80 and lab.notified_80:
            lab.notified_80 = False
        if utilization_pct < 50 and lab.notified_50:
            lab.notified_50 = False
        # ----------------------

        threshold_hit = None
        if utilization_pct >= 95 and not lab.notified_95:
            threshold_hit = 95
            lab.notified_95 = True
            lab.notified_80 = True 
            lab.notified_50 = True
        elif utilization_pct >= 80 and not lab.notified_80:
            threshold_hit = 80
            lab.notified_80 = True
            lab.notified_50 = True
        elif utilization_pct >= 50 and not lab.notified_50:
            threshold_hit = 50
            lab.notified_50 = True

        db.commit() 

        if not threshold_hit:
            return 

        # Gather recipients and send email
        recipients = []
        lab_ic = db.query(User).filter(User.lab_id == lab.lab_id, User.role_id == 3).first()
        
        # --- RUFF FIX: Break statements onto new lines ---
        if lab_ic and lab_ic.email:
            recipients.append(lab_ic.email)

        team_lead = db.query(User).filter(User.lab_group_id == lab.lab_group_id, User.role_id == 2).first()
        
        if team_lead and team_lead.email:
            recipients.append(team_lead.email)

        if not recipients:
            return
        # -------------------------------------------------

        spent_str = f"${float(total_spent):,.2f}"
        budget_str = f"${float(total_budget):,.2f}"
        
        if threshold_hit == 50:
            subject, color = f"Notice: {lab.lab_name} has reached 50% Budget Utilization", "#2563eb"
            message = "You have utilized half of your allocated lab budget. Please review upcoming planned expenses."
        elif threshold_hit == 80:
            subject, color = f"WARNING: {lab.lab_name} has reached 80% Budget Utilization", "#d97706" 
            message = "Your lab is approaching its budget limit. Please prioritize essential purchases only."
        else: 
            subject, color = f"CRITICAL: {lab.lab_name} has reached 95% Budget Utilization", "#dc2626" 
            message = "Immediate attention required. Your lab budget is nearly exhausted. Further PRs may be rejected unless additional funding is secured."

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
                <p style="font-size: 16px; color: {color}; font-weight: bold;">{message}</p>
                <p style="font-size: 14px; color: #6b7280; margin-top: 30px;">
                    Please log in to the SIT Lab Budget System to review your purchase lines.
                </p>
            </div>
        </div>
        """
        send_threshold_alert(recipients, subject, html_body)